"""Rule-based project intelligence: features -> MissingnessGraph -> CompletionPlans (typed ops)."""
import hashlib
import json

MODES = ["Clean", "Hybrid", "Industrial", "Hypnotic", "Dub Techno", "Raw Warehouse", "Minimal Driving", "Peak Time"]
MODE_PROFILE = {
    "Clean": {"sc_depth": .45, "hum": 6}, "Hybrid": {"sc_depth": .55, "hum": 8}, "Industrial": {"sc_depth": .7, "hum": 4},
    "Hypnotic": {"sc_depth": .5, "hum": 10}, "Dub Techno": {"sc_depth": .6, "hum": 12}, "Raw Warehouse": {"sc_depth": .65, "hum": 14},
    "Minimal Driving": {"sc_depth": .5, "hum": 6}, "Peak Time": {"sc_depth": .75, "hum": 5},
}


def _pid(rev, key):
    return "plan_" + hashlib.sha1(f"{rev}:{key}".encode()).hexdigest()[:10]


def features(p):
    by_role = {}
    for t in p["tracks"]:
        by_role.setdefault(t["role"], []).append(t)
    dens = {t["id"]: round(sum(1 for s in t["pattern"] if s["on"]) / max(1, len(t["pattern"])), 3) for t in p["tracks"]}
    sc_targets = {g["track"] for sc in p["sidechains"] if sc.get("enabled", True) for g in sc["targets"]}
    kick = by_role.get("kick", [None])[0]
    kick_steps = {i for i, s in enumerate(kick["pattern"]) if s["on"]} if kick else set()
    clashes = []
    for r in by_role.get("rumble", []):
        L = len(r["pattern"])
        clashes += [(r["id"], i) for i, s in enumerate(r["pattern"]) if s["on"] and L == 16 and i in kick_steps]
    return {
        "roles": sorted(by_role), "density": dens, "sidechain_targets": sorted(sc_targets),
        "kick_four_on_floor": kick is not None and kick_steps >= {0, 4, 8, 12},
        "pattern_lengths": {t["id"]: len(t["pattern"]) for t in p["tracks"]},
        "sections": [s["name"] for s in p["sections"]], "automation_lanes": [ln["target"] for ln in p["automation"]],
        "low_end_clashes": clashes, "bpm": p["bpm"], "key": f"{p['key']} {p['scale']}",
        "analysis_basis": "MIDI/pattern-derived inference (no audio measurement)",
    }


def plans(p, mode="Hybrid"):
    f = features(p)
    prof = MODE_PROFILE.get(mode, MODE_PROFILE["Hybrid"])
    rev = p["revision"]
    out = []
    secs = p["sections"]
    start_of = lambda i: sum(s["bars"] for s in secs[:i])
    sec_idx = lambda name: next((i for i, s in enumerate(secs) if s["name"] == name), None)
    tr = {t["id"]: t for t in p["tracks"]}
    kick = next((t for t in p["tracks"] if t["role"] == "kick"), None)

    def add(key, kind, title, targets, bars, ops, rationale, conf, risk, outcome, manual, fact):
        out.append({"id": _pid(rev, key), "revision": rev, "kind": kind, "title": title, "targets": targets,
                    "start_bar": bars[0], "end_bar": bars[1], "operations": ops, "rationale": rationale,
                    "confidence": conf, "risk": risk, "expected_outcome": outcome, "manual_steps": manual,
                    "finding": fact, "previewable": True, "executable": True,
                    "compatibility": "In-app engine: supported. Native .als: manual steps only (no verified device template).",
                    "undo": "Reverts via project history (one undo step per applied operation)."})

    total = p.get("length_bars", 0) or 16
    for role, label in (("kick", "909 kick"), ("hats", "909 offbeat hats"), ("perc", "industrial polyrhythm percussion"), ("stabs", "dub stabs"), ("rumble", "rumble sub")):
        if role not in f["roles"]:
            add(f"add_{role}", "missing_layer", f"Add {label} layer", [role], (0, total),
                [{"type": "AddLayer", "role": role, "seed": p["seed"], "origin": "ai"}],
                f"No {role} track exists; the groove lacks this functional layer.", 0.9, "low",
                f"A new editable {label} track joins the arrangement.",
                [f"Create a MIDI track named {role.upper()}.", "Load the native chain listed for this layer in the Generators reference.",
                 "Copy the generated pattern (export MIDI) onto the track."], "confirmed structural fact")
    if kick:
        for t in p["tracks"]:
            if t["role"] in ("rumble", "stabs") and t["id"] not in f["sidechain_targets"]:
                depth = prof["sc_depth"] if t["role"] == "rumble" else round(prof["sc_depth"] * 0.6, 2)
                add(f"sc_{t['id']}", "sidechain", f"Sidechain {t['name']} from SC_KICK", [kick["id"], t["id"]], (0, total),
                    [{"type": "ConfigureSidechain", "source": kick["id"], "target": t["id"], "depth": depth, "release_ms": 140}],
                    f"{t['name']} plays against the kick without ducking; low-mid energy masks the transient.", 0.85, "low",
                    "Kick punches through; the layer pumps on each hit.",
                    [f"Track: {t['name']}", "Device: Compressor (insert last in chain)", f"Sidechain: ON, Audio From: SC_KICK (Post FX)",
                     f"Ratio 4:1, Attack 0.1 ms, Release 140 ms, Threshold so GR peaks ≈ {depth * 12:.0f} dB",
                     "Verify: watch gain reduction meter on every kick; solo kick + layer to confirm separation."],
                    "confirmed structural fact")
    for rid, i in f["low_end_clashes"][:1]:
        steps = [s for (r, s) in f["low_end_clashes"] if r == rid]
        add(f"clash_{rid}", "low_end", f"Remove sub notes colliding with kick ({len(steps)})", [rid], (0, total),
            [{"type": "UpdateStep", "track": rid, "index": s, "fields": {"on": False}} for s in steps],
            "Sub notes start on the same 16th as the kick; both occupy 40-80 Hz simultaneously.", 0.75, "medium",
            "Cleaner low end; kick and rumble alternate.",
            [f"Open the {tr[rid]['name']} clip.", f"Delete notes on steps {', '.join(str(s + 1) for s in steps)} (kick positions)."],
            "inferred from MIDI positions")
    if secs and sec_idx("Breakdown") is None:
        at = (sec_idx("Groove") + 1) if sec_idx("Groove") is not None else len(secs)
        add("breakdown", "structure", "Insert 8-bar breakdown", [t["id"] for t in p["tracks"] if t["role"] in ("stabs", "perc", "hats")],
            (start_of(at), start_of(at) + 8), [{"type": "GenerateArrangementSection", "kind": "Breakdown", "bars": 8, "index": at, "origin": "ai"}],
            "Arrangement has no breakdown; energy never drops before the peak.", 0.7, "low",
            "Kick-less tension section before the drop.",
            [f"At bar {start_of(at) + 1}, insert 8 bars of time (Cmd+I).", "Mute KICK and RUMBLE in this region; keep stabs/perc/hats."],
            "confirmed structural fact")
    bi = sec_idx("Breakdown")
    if bi is not None and "master.cutoff" not in f["automation_lanes"]:
        b0, b1 = start_of(bi), start_of(bi) + secs[bi]["bars"]
        add("riser", "automation", "Master filter riser through breakdown", ["master"], (b0, b1),
            [{"type": "SetAutomationLane", "target": "master.cutoff", "curve": "exp", "source": "ai",
              "points": [{"bar": max(0, b0 - 0.01), "value": 20000}, {"bar": b0, "value": 400}, {"bar": b1 - 0.25, "value": 12000}, {"bar": b1, "value": 20000}]}],
            "No transition automation into the drop; the breakdown→drop boundary is static.", 0.7, "low",
            "Low-pass opens over the breakdown and snaps open at the drop.",
            ["Track: Main", "Device: Auto Filter (Lowpass, 24 dB)", f"Automate Frequency: bar {b0 + 1} = 400 Hz → bar {b1} = 12 kHz (exponential)",
             f"At bar {b1 + 1} return to 20 kHz.", "Verify: sweep audibly opens; no clicks at the jump."], "inferred artistic suggestion")
    for t in p["tracks"]:
        if t["role"] == "perc" and len(t["pattern"]) == 16:
            add(f"poly_{t['id']}", "variation", f"Make {t['name']} polyrhythmic (7 steps)", [t["id"]], (0, total),
                [{"type": "SetPatternLength", "track": t["id"], "length": 7}],
                "Percussion loops on the same 16-step cycle as everything else → excessive repetition.", 0.6, "medium",
                "Accent pattern drifts against the bar, phasing over 7 bars.",
                [f"Set {t['name']} clip loop length to 7/16 (1.3.3 → 1.0.0 + 7 sixteenths)."], "inferred artistic suggestion")
        if t["role"] in ("hats", "perc") and all(abs(s.get("micro", 0)) < 0.01 for s in t["pattern"] if s["on"]):
            add(f"hum_{t['id']}", "groove", f"Humanize {t['name']}", [t["id"]], (0, total),
                [{"type": "ApplyHumanization", "track": t["id"], "micro_ms": prof["hum"], "ghost_pct": 18, "seed": p["seed"]}],
                "All hits sit exactly on the grid with flat velocities (mechanical).", 0.65, "low",
                "Subtle push/pull and ghost dynamics; kick stays grid-locked.",
                [f"Select all notes in {t['name']}.", f"Apply Groove Pool 'Swing 16-55' with Timing {prof['hum'] * 4}%, Random 10%, Velocity 18%."],
                "inferred from MIDI timing")
    return {"mode": mode, "features": f, "missingness": [{"kind": x["kind"], "finding": x["finding"], "title": x["title"]} for x in out],
            "plans": out}


def explain_context(plan):
    keep = {k: plan[k] for k in ("title", "kind", "rationale", "operations", "start_bar", "end_bar", "risk", "expected_outcome")}
    return json.dumps(keep)
