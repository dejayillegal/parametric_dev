"""Typed, validated operations on a Parametric project (in-app ProjectGraph).

Every mutation goes through apply_op. Undo is deterministic: the server stores the
pre-operation snapshot for every applied operation (see server.py history).
"""
import copy

from . import composer as C
from .dsp import AUTOMATION_TARGETS

OP_TYPES = ["SetTempo", "SetKey", "ToggleStep", "UpdateStep", "SetPatternLength", "RotatePattern", "SetTrackParam",
            "SetSynthParam", "SetMacro", "ApplyMacroSnapshot", "RegenerateLayer", "AddLayer", "DeleteTrack",
            "ConfigureSidechain", "SetAutomationLane", "DeleteAutomationLane", "ToggleSectionTrack",
            "GenerateArrangementSection", "ApplyHumanization", "SetXY", "RenameProject", "RecordPerformance"]


class OpError(ValueError):
    pass


def _track(p, tid):
    for t in p["tracks"]:
        if t["id"] == tid:
            return t
    raise OpError(f"Track '{tid}' does not exist")


def _rng(v, lo, hi, name):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"{name} must be a number")
    if not (lo <= v <= hi):
        raise OpError(f"{name}={v} outside valid range [{lo}, {hi}]")
    return v


def apply_op(p, op):
    """Mutates p in place. Returns a short human description of the change."""
    t = op.get("type")
    if t not in OP_TYPES:
        raise OpError(f"Unsupported operation type '{t}'")
    if t == "SetTempo":
        p["bpm"] = _rng(op["bpm"], 60, 200, "bpm")
        return f"Tempo -> {p['bpm']:.2f} BPM"
    if t == "SetKey":
        if op["key"] not in C.KEYS or op["scale"] not in C.SCALES:
            raise OpError("Unknown key or scale")
        delta = (C.KEYS.index(op["key"]) - C.KEYS.index(p["key"]) + 6) % 12 - 6
        for tr in p["tracks"]:
            if tr["role"] in ("rumble", "stabs"):
                for s in tr["pattern"]:
                    if "pitch" in s:
                        s["pitch"] = int(s["pitch"] + delta)
        p["key"], p["scale"] = op["key"], op["scale"]
        return f"Key -> {op['key']} {op['scale']} (pitched tracks transposed {delta:+d} st)"
    if t in ("ToggleStep", "UpdateStep"):
        tr = _track(p, op["track"])
        i = int(op["index"])
        if not 0 <= i < len(tr["pattern"]):
            raise OpError("Step index out of range")
        s = tr["pattern"][i]
        if t == "ToggleStep":
            s["on"] = not s["on"]
            return f"{tr['name']} step {i + 1} {'on' if s['on'] else 'off'}"
        f = op.get("fields", {})
        lim = {"vel": (1, 127), "prob": (0, 1), "ratchet": (1, 4), "micro": (-25, 25), "gate": (0.1, 16), "pitch": (0, 127)}
        for k, v in f.items():
            if k == "on":
                s["on"] = bool(v)
            elif k in lim:
                val = _rng(v, *lim[k], k)
                s[k] = int(val) if k in ("vel", "ratchet", "pitch") else val
            elif k == "chord":
                if not isinstance(v, list) or not all(isinstance(x, int) and -24 <= x <= 24 for x in v):
                    raise OpError("chord must be list of intervals")
                s["chord"] = v
            else:
                raise OpError(f"Unknown step field '{k}'")
        return f"{tr['name']} step {i + 1} updated"
    if t == "SetPatternLength":
        tr = _track(p, op["track"])
        n = int(_rng(op["length"], 1, 64, "length"))
        pat = tr["pattern"]
        tmpl = dict(pat[0]) if pat else C.step()
        tmpl["on"] = False
        tr["pattern"] = (pat + [dict(tmpl) for _ in range(n)])[:n]
        return f"{tr['name']} length -> {n} steps"
    if t == "RotatePattern":
        tr = _track(p, op["track"])
        k = int(op.get("amount", 1)) % max(1, len(tr["pattern"]))
        tr["pattern"] = tr["pattern"][-k:] + tr["pattern"][:-k] if k else tr["pattern"]
        return f"{tr['name']} rotated {k}"
    if t == "SetTrackParam":
        tr = _track(p, op["track"])
        k, v = op["key"], op["value"]
        if k in ("mute", "solo"):
            tr[k] = bool(v)
        elif k == "volume":
            tr[k] = _rng(v, -60, 6, "volume")
        elif k == "pan":
            tr[k] = _rng(v, -1, 1, "pan")
        elif k == "send_a":
            tr[k] = _rng(v, 0, 1, "send_a")
        elif k == "name":
            if not str(v).strip() or len(str(v)) > 40:
                raise OpError("Name must be 1-40 chars")
            tr[k] = str(v).strip()
        else:
            raise OpError(f"Unknown track param '{k}'")
        return f"{tr['name']} {k} -> {tr[k]}"
    if t == "SetSynthParam":
        tr = _track(p, op["track"])
        spec = C.ROLE_PARAMS[tr["role"]].get(op["key"])
        if not spec:
            raise OpError(f"'{op['key']}' is not a parameter of {tr['role']}")
        tr["synth"][op["key"]] = _rng(op["value"], spec[0], spec[1], op["key"])
        return f"{tr['name']} {op['key']} -> {tr['synth'][op['key']]:.3f} {spec[3]}"
    if t == "SetMacro":
        i = int(_rng(op["index"], 0, 7, "index"))
        p["macros"][i] = _rng(op["value"], 0, 1, "value")
        return f"Macro {i + 1} -> {p['macros'][i]:.2f}"
    if t == "ApplyMacroSnapshot":
        name = op["name"]
        mix = _rng(op.get("amount", 1.0), 0, 1, "amount")
        target = p["template_macros"] if name == "Reset" else C.SNAPSHOTS.get(name)
        if target is None:
            raise OpError(f"Unknown snapshot '{name}'")
        p["macros"] = [m if tv is None else round(m + (tv - m) * mix, 4) for m, tv in zip(p["macros"], target)]
        return f"Snapshot {name} ({mix * 100:.0f}%)"
    if t == "RegenerateLayer":
        tr = _track(p, op["track"])
        seed = int(op.get("seed", tr.get("layer_seed", p["seed"]) + 1))
        preset = op.get("preset", tr.get("preset"))
        if tr["role"] == "rumble" and preset and preset not in C.RUMBLE_PRESETS:
            raise OpError("Unknown rumble preset")
        tr["pattern"] = C.gen_pattern(tr["role"], seed, p["params"], p["key"], p["scale"], preset)
        tr["layer_seed"], tr["preset"] = seed, preset
        tr["provenance"]["seed"] = seed
        if tr["role"] == "rumble" and preset:
            tr["synth"]["rumble_amount"] = C.RUMBLE_PRESETS[preset]["amount"]
        return f"{tr['name']} regenerated (seed {seed})"
    if t == "AddLayer":
        role = op["role"]
        if role not in C.ROLE_META:
            raise OpError("Unknown layer role")
        idx = sum(1 for tr in p["tracks"] if tr["role"] == role)
        if idx >= 4:
            raise OpError("Max 4 tracks per layer type")
        preset = op.get("preset") or ("clean_warehouse" if role == "rumble" else None)
        tr = C.make_track(role, int(op.get("seed", p["seed"])), p["params"], p["key"], p["scale"], idx, preset)
        tr["provenance"]["origin"] = op.get("origin", "user")
        p["tracks"].append(tr)
        if not p["sections"]:
            p["sections"] = [{"name": "Loop", "bars": 8, "active": []}]
        for s in p["sections"]:
            if s["name"] not in ("Intro", "Outro") or role in ("kick", "hats"):
                s["active"].append(tr["id"])
        p["length_bars"] = sum(s["bars"] for s in p["sections"])
        return f"Added {tr['name']}"
    if t == "DeleteTrack":
        tr = _track(p, op["track"])
        p["tracks"].remove(tr)
        for s in p["sections"]:
            s["active"] = [x for x in s["active"] if x != tr["id"]]
        for sc in p["sidechains"]:
            sc["targets"] = [g for g in sc["targets"] if g["track"] != tr["id"]]
        p["sidechains"] = [sc for sc in p["sidechains"] if sc["source"] != tr["id"]]
        return f"Deleted {tr['name']}"
    if t == "ConfigureSidechain":
        src = _track(p, op["source"])
        if src["role"] != "kick":
            raise OpError("In-app sidechain trigger must be a kick track (SC_KICK tap)")
        tgt = _track(p, op["target"])
        if tgt["id"] == src["id"]:
            raise OpError("A track cannot sidechain itself")
        sc = next((s for s in p["sidechains"] if s["source"] == src["id"]), None)
        if sc is None:
            sc = {"id": f"sc_{len(p['sidechains']) + 1}", "source": src["id"], "enabled": True, "status": "confirmed", "targets": []}
            p["sidechains"].append(sc)
        sc["targets"] = [g for g in sc["targets"] if g["track"] != tgt["id"]]
        if op.get("enabled", True):
            sc["targets"].append({"track": tgt["id"], "depth": _rng(op.get("depth", 0.5), 0, 1, "depth"),
                                  "release_ms": _rng(op.get("release_ms", 140), 20, 800, "release_ms")})
            return f"Sidechain {src['name']} -> {tgt['name']}"
        return f"Sidechain removed from {tgt['name']}"
    if t == "SetAutomationLane":
        tgt = op["target"]
        spec = AUTOMATION_TARGETS.get(tgt)
        if not spec:
            raise OpError(f"Unknown automation target '{tgt}'")
        pts = op.get("points", [])
        if not pts:
            raise OpError("Automation lane needs points")
        clean = []
        for pt in pts:
            clean.append({"bar": _rng(pt["bar"], 0, 512, "bar"), "value": _rng(pt["value"], spec["min"], spec["max"], tgt)})
        if op.get("curve", "linear") not in ("linear", "exp", "step", "s"):
            raise OpError("curve must be linear|exp|step|s")
        p["automation"] = [ln for ln in p["automation"] if ln["target"] != tgt]
        p["automation"].append({"id": f"lane_{tgt}", "target": tgt, "curve": op.get("curve", "linear"), "enabled": True,
                                "source": op.get("source", "user"), "points": sorted(clean, key=lambda x: x["bar"])})
        return f"Automation {tgt}: {len(clean)} points"
    if t == "DeleteAutomationLane":
        before = len(p["automation"])
        p["automation"] = [ln for ln in p["automation"] if ln["target"] != op["target"]]
        if len(p["automation"]) == before:
            raise OpError("No such lane")
        return f"Automation {op['target']} removed"
    if t == "ToggleSectionTrack":
        i = int(op["section"])
        if not 0 <= i < len(p["sections"]):
            raise OpError("Section out of range")
        tr = _track(p, op["track"])
        a = p["sections"][i]["active"]
        if tr["id"] in a:
            a.remove(tr["id"])
        else:
            a.append(tr["id"])
        return f"{p['sections'][i]['name']}: {tr['name']} {'on' if tr['id'] in a else 'off'}"
    if t == "GenerateArrangementSection":
        kind = op.get("kind", "Breakdown")
        bars = int(_rng(op.get("bars", 8), 1, 64, "bars"))
        roles = {"Breakdown": ("stabs", "perc", "hats"), "Build": ("kick", "hats", "perc", "rumble"),
                 "Drop": ("kick", "hats", "perc", "rumble", "stabs"), "Intro": ("kick", "hats"), "Outro": ("kick", "hats")}.get(kind)
        if roles is None:
            raise OpError("Unknown section kind")
        active = [tr["id"] for tr in p["tracks"] if tr["role"] in roles]
        at = int(op.get("index", len(p["sections"])))
        at = max(0, min(at, len(p["sections"])))
        p["sections"].insert(at, {"name": kind, "bars": bars, "active": active, "origin": op.get("origin", "user")})
        p["length_bars"] = sum(s["bars"] for s in p["sections"])
        return f"Inserted {kind} ({bars} bars) at section {at + 1}"
    if t == "ApplyHumanization":
        tr = _track(p, op["track"])
        tr["pattern"] = C.humanize(tr["pattern"], int(op.get("seed", p["seed"])), _rng(op.get("micro_ms", 8), 0, 25, "micro_ms"),
                                   _rng(op.get("ghost_pct", 15), 0, 35, "ghost_pct"), tr["role"])
        return f"{tr['name']} humanized"
    if t == "SetXY":
        p["xy"] = {"x": _rng(op["x"], 0, 1, "x"), "y": _rng(op["y"], 0, 1, "y")}
        return f"XY -> {p['xy']['x']:.2f}, {p['xy']['y']:.2f}"
    if t == "RenameProject":
        if not str(op["name"]).strip():
            raise OpError("Name required")
        p["name"] = str(op["name"]).strip()[:60]
        return f"Renamed to {p['name']}"
    if t == "RecordPerformance":
        # Captured scene launches become arrangement sections, in launch order.
        launches = op.get("launches", [])
        if not launches:
            raise OpError("Nothing recorded")
        new = []
        for ln in launches:
            i = int(ln["section"])
            if not 0 <= i < len(p["sections"]):
                raise OpError("Recorded scene index out of range")
            src = p["sections"][i]
            new.append({"name": f"{src['name']} (rec)", "bars": int(_rng(ln.get("bars", src["bars"]), 1, 64, "bars")),
                        "active": list(src["active"]), "origin": "performance"})
        p["sections"] = new
        p["length_bars"] = sum(s["bars"] for s in new)
        return f"Recorded {len(new)} scene launches into arrangement"
    raise OpError("unreachable")


def preview(p, ops):
    q = copy.deepcopy(p)
    for op in ops:
        apply_op(q, op)
    return q
