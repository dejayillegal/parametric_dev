"""Deterministic techno composition engine. Same seed + params => same project."""
import random

KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SCALES = {
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}

TEMPLATES = {
    "berghain": {"name": "Berghain 04:00 AM", "bpm": 132, "key": "F", "scale": "phrygian", "rumble_preset": "heavy_rumble",
                 "params": {"density": .6, "tension": .55, "groove": .3, "distortion": .4, "hypnotic": .8, "width": .6, "variation": .4},
                 "macros": [.45, .55, .35, .45, .4, 0, .45, .5]},
    "tresor": {"name": "Tresor Industrial Vault", "bpm": 138, "key": "D", "scale": "phrygian", "rumble_preset": "rolling_industrial",
               "params": {"density": .75, "tension": .7, "groove": .15, "distortion": .8, "hypnotic": .5, "width": .5, "variation": .5},
               "macros": [.5, .4, .7, .3, .3, .15, .35, .4]},
    "detroit": {"name": "Detroit Warehouse 1994", "bpm": 128, "key": "A", "scale": "dorian", "rumble_preset": "dub_sub",
                "params": {"density": .55, "tension": .4, "groove": .5, "distortion": .25, "hypnotic": .45, "width": .7, "variation": .6},
                "macros": [.55, .3, .25, .55, .5, 0, .5, .55]},
}

RUMBLE_PRESETS = {
    "clean_warehouse": {"name": "Clean Warehouse", "offsets": [2, 6, 10, 14], "gate": 1.5, "amount": .35},
    "heavy_rumble": {"name": "Heavy Rumble", "offsets": [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15], "gate": .9, "amount": .8},
    "rolling_industrial": {"name": "Rolling Industrial", "offsets": [1, 3, 5, 7, 9, 11, 13, 15, 2, 10], "gate": .7, "amount": .65},
    "dub_sub": {"name": "Dub Sub", "offsets": [3, 7, 11, 15], "gate": 2.5, "amount": .45},
    "minimal_pressure": {"name": "Minimal Pressure", "offsets": [2, 10], "gate": 1.2, "amount": .55},
}

ROLE_PARAMS = {
    "kick": {"pitch": (40, 70, 50, "Hz"), "depth": (50, 400, 180, "Hz"), "pitch_decay": (0.01, 0.12, 0.035, "s"),
             "amp_decay": (0.1, 1.0, 0.38, "s"), "click": (0, 1, 0.4, ""), "saturation": (1, 6, 1.6, "x")},
    "rumble": {"sub_decay": (0.05, 1.0, 0.25, "s"), "rumble_amount": (0, 1, 0.6, ""), "saturation": (1, 6, 2.0, "x")},
    "perc": {"freq": (150, 2000, 520, "Hz"), "ratio": (1, 4, 1.41, ":1"), "index": (0, 10, 4, ""), "decay": (0.02, 0.5, 0.09, "s")},
    "hats": {"closed_decay": (0.01, 0.15, 0.035, "s"), "open_decay": (0.08, 0.6, 0.22, "s"), "tone": (4000, 12000, 7000, "Hz")},
    "stabs": {"cutoff": (200, 8000, 1400, "Hz"), "env_amt": (0, 1, 0.5, ""), "detune": (0, 40, 12, "ct"), "delay_steps": (1, 6, 3, "16th")},
}

ROLE_META = {
    "kick": ("KICK", "DRUMS", "#EF4444", "909-inspired kick synth"),
    "rumble": ("RUMBLE SUB", "BASS", "#F59E0B", "Rumble Sub Bass"),
    "perc": ("IND PERC", "DRUMS", "#A3A3A3", "Industrial Polyrhythm Percussion"),
    "hats": ("909 HATS", "DRUMS", "#06B6D4", "909 Offbeat & Ghost Hats"),
    "stabs": ("DUB STABS", "SYNTHS", "#22C55E", "Hypnotic Dub Synth Stabs"),
}

NATIVE_TARGETS = {
    "kick": "Drum Rack > Simpler (kick one-shot)",
    "rumble": "Operator (Sine) -> Reverb -> EQ Eight -> Compressor (sidechain)",
    "perc": "Collision -> Drum Buss -> Erosion -> Saturator",
    "stabs": "Wavetable -> Echo -> Auto Pan",
    "hats": "Simpler -> Overdrive -> Auto Filter",
}

SNAPSHOTS = {
    "Tension Riser": [.75, .5, .6, .65, .35, .1, .55, .7],
    "Sub Cut": [.02, .2, None, None, None, None, None, None],
    "Dub Wash": [None, .7, .2, .85, .6, 0, .8, .78],
    "Industrial Breakdown": [.3, .8, .9, .3, .25, .45, .4, .5],
    "Peak-Time Pressure": [.6, .45, .65, .35, .35, .1, .3, .4],
}


def step(on=False, vel=100, pitch=None, gate=1.0, prob=1.0, ratchet=1, micro=0.0, chord=None):
    s = {"on": on, "vel": vel, "prob": prob, "ratchet": ratchet, "micro": micro, "gate": gate}
    if pitch is not None:
        s["pitch"] = pitch
    if chord is not None:
        s["chord"] = chord
    return s


def euclid(k, n, rot=0):
    pat = [((i * k) % n) < k for i in range(n)]
    return pat[-rot:] + pat[:-rot] if rot else pat


def default_synth(role):
    return {k: v[2] for k, v in ROLE_PARAMS[role].items()}


def root_midi(key, octave):
    return 12 * (octave + 1) + KEYS.index(key)


def gen_pattern(role, seed, p, key, scale, preset=None):
    rng = random.Random(f"{seed}:{role}:{preset}")
    d, v, g, t = p["density"], p["variation"], p["groove"], p["tension"]
    if role == "kick":
        pat = [step(i % 4 == 0, 127) for i in range(16)]
        if t > 0.65 and rng.random() < v:
            pat[14] = step(True, 70)
        return pat
    if role == "rumble":
        pr = RUMBLE_PRESETS[preset or "heavy_rumble"]
        root = root_midi(key, 1)
        sc = SCALES[scale]
        core = pr["offsets"][:2]
        pat = [step(False, 90, root, pr["gate"]) for _ in range(16)]
        for o in pr["offsets"]:
            if o in core or rng.random() < 0.35 + d * 0.65:
                vel = 110 if o % 4 == 2 else int(70 + rng.random() * 30)
                pitch = root
                if rng.random() < v * 0.25:
                    pitch = root + rng.choice([sc[1], sc[4], 12])
                pat[o] = step(True, vel, pitch, pr["gate"])
        return pat
    if role == "perc":
        n = rng.choice([3, 5, 7])
        k = {3: 1, 5: 2, 7: 3}[n]
        hits = euclid(k, n, rng.randrange(n))
        notes = [60, 63, 67, 70]
        pat = []
        for i in range(n):
            on = hits[i] or rng.random() < d * 0.3
            vel = int(105 + rng.random() * 20) if hits[i] else int(35 + rng.random() * 20)
            pat.append(step(on, vel, rng.choice(notes), 1.0, 1.0 if hits[i] else 0.6 + 0.4 * d,
                            2 if rng.random() < d * 0.2 else 1))
        return pat
    if role == "hats":
        pat = []
        for i in range(16):
            if i % 4 == 2:
                pat.append(step(True, int(100 + rng.random() * 15), 46))
            else:
                on = i % 4 != 0 and rng.random() < 0.3 + d * 0.7
                ghost = i % 2 == 1
                vel = int(28 + rng.random() * 25) if ghost else int(70 + rng.random() * 25)
                pat.append(step(on, vel, 42, 1.0, 0.85 if ghost else 1.0))
        return humanize(pat, seed, g * 12, g * 35, "hats")
    if role == "stabs":
        sc = SCALES[scale]
        root = root_midi(key, 3)
        degrees = [0, 1] if scale == "phrygian" else [0, 5, 3]
        slots = [3, 6, 10, 14, 19, 22, 27, 30]
        chosen = [s for s in slots if rng.random() < 0.3 + d * 0.5] or [3, 19]
        pat = [step(False, 90, root, 1.0) for _ in range(32)]
        for s in chosen:
            deg = degrees[(s // 16) % len(degrees)] if rng.random() > v * 0.5 else rng.choice(degrees)
            pitch = root + sc[deg % 7]
            chord = [0, 3, 7] if rng.random() > t * 0.6 else rng.choice([[0, 3, 7, 10], [0, 3, 6], [0, 1, 7], [0, 5, 7]])
            if rng.random() < v * 0.5:
                chord = chord[1:] + [chord[0] + 12]  # inversion
            pat[s] = step(True, int(85 + rng.random() * 30), pitch, round(0.8 + rng.random() * 1.2, 2), chord=chord)
        return pat
    raise ValueError(role)


def humanize(pat, seed, micro_ms, ghost_pct, role):
    """Gaussian microtiming (clamped 0-25 ms) + velocity ghosting (0-35%). Kick stays grid-locked."""
    if role == "kick":
        return pat
    rng = random.Random(f"{seed}:humanize:{role}")
    micro_ms = min(25.0, max(0.0, micro_ms))
    ghost_pct = min(35.0, max(0.0, ghost_pct))
    out = []
    for i, s in enumerate(pat):
        s = dict(s)
        if s["on"]:
            s["micro"] = round(max(-25, min(25, rng.gauss(0, micro_ms / 2.5))), 2) if micro_ms > 0 else 0.0
            if i % 4 != 0:
                s["vel"] = int(max(1, min(127, s["vel"] * (1 - ghost_pct / 100 * rng.random()))))
        out.append(s)
    return out


def make_track(role, seed, p, key, scale, idx=0, preset=None):
    name, group, color, _ = ROLE_META[role]
    tid = f"trk_{role}" if idx == 0 else f"trk_{role}_{idx}"
    synth = default_synth(role)
    if role == "rumble":
        synth["rumble_amount"] = RUMBLE_PRESETS[preset or "heavy_rumble"]["amount"]
    return {"id": tid, "role": role, "name": name if idx == 0 else f"{name} {idx + 1}", "group": group, "color": color,
            "mute": False, "solo": False, "volume": {"kick": -2.0, "rumble": -4.0, "perc": -8.0, "hats": -7.0, "stabs": -9.0}[role],
            "pan": 0.0, "send_a": {"kick": 0.0, "rumble": 0.0, "perc": 0.35, "hats": 0.15, "stabs": 0.5}[role],
            "synth": synth, "preset": preset, "layer_seed": seed,
            "pattern": gen_pattern(role, seed, p, key, scale, preset),
            "provenance": {"origin": "generator", "generator": ROLE_META[role][3], "seed": seed,
                           "native_target": NATIVE_TARGETS[role], "native_export": "manual-only (no verified device template)"}}


def make_sections(tids, length):
    has = lambda r: f"trk_{r}" in tids
    pick = lambda *rs: [f"trk_{r}" for r in rs if has(r)]
    u = max(4, length // 8)
    secs = [("Intro", u, pick("kick", "hats")), ("Build", u, pick("kick", "hats", "perc", "rumble")),
            ("Groove", u * 2, pick("kick", "hats", "perc", "rumble")), ("Breakdown", u, pick("stabs", "perc", "hats")),
            ("Drop", u * 2, pick("kick", "hats", "perc", "rumble", "stabs")), ("Outro", u, pick("kick", "hats"))]
    return [{"name": n, "bars": b, "active": a} for n, b, a in secs]


def new_project(template="berghain", seed=1, name=None, bpm=None, key=None, scale=None, params=None, length=64):
    if template == "empty":
        tpl = {"name": "Untitled", "bpm": 130, "key": "A", "scale": "minor", "rumble_preset": "clean_warehouse",
               "params": {"density": .5, "tension": .5, "groove": .3, "distortion": .3, "hypnotic": .5, "width": .5, "variation": .4},
               "macros": [.5, .4, .3, .3, .4, 0, .4, .4]}
    else:
        tpl = TEMPLATES[template]
    p = dict(tpl["params"])
    p.update(params or {})
    key = key or tpl["key"]
    scale = scale or tpl["scale"]
    tracks = []
    if template != "empty":
        for role in ["kick", "rumble", "perc", "hats", "stabs"]:
            tracks.append(make_track(role, seed, p, key, scale, 0, tpl["rumble_preset"] if role == "rumble" else None))
    tids = {t["id"] for t in tracks}
    sections = make_sections(tids, length) if tracks else []
    auto = []
    sc = []
    if tracks:
        b0 = sum(s["bars"] for s in sections[:3])
        b1 = b0 + sections[3]["bars"]
        auto.append({"id": "lane_1", "target": "stabs.cutoff", "curve": "exp", "enabled": True, "source": "template",
                     "points": [{"bar": 0, "value": 600}, {"bar": b0, "value": 500}, {"bar": b1, "value": 4500}, {"bar": b1 + 1, "value": 1400}]})
        sc.append({"id": "sc_1", "source": "trk_kick", "enabled": True, "status": "confirmed",
                   "targets": [{"track": "trk_rumble", "depth": 0.6, "release_ms": 140}]})
    return {"name": name or (tpl["name"] if template != "empty" else "Untitled"), "template": template, "seed": int(seed),
            "bpm": float(bpm or tpl["bpm"]), "time_sig": [4, 4], "key": key, "scale": scale, "params": p,
            "length_bars": sum(s["bars"] for s in sections), "macros": list(tpl["macros"]), "template_macros": list(tpl["macros"]),
            "xy": {"x": 1.0, "y": 0.0}, "tracks": tracks, "sections": sections, "automation": auto, "sidechains": sc,
            "revision": 1, "source": "generated"}
