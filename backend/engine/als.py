"""Ableton Live Set (.als) reader, validator and minimal source-preserving patch compiler.

Layers: container detection -> safe XML parse (RawXmlLayer: original bytes kept verbatim)
-> version adapter -> semantic summary (ProjectGraph view) -> invariants.

Writes are line-level text patches of single attribute values on the ORIGINAL source;
every other byte is preserved. Native reopen in Ableton is NOT verified here.
"""
import difflib
import gzip
import hashlib
import math
import re
import zlib
from collections import Counter

from lxml import etree

MAX_COMPRESSED = 15 * 1024 * 1024
MAX_DECOMPRESSED = 200 * 1024 * 1024
PREROLL = -63072000.0

COMPAT = {
    10: {"import": True, "inspect": True, "audio_preview": False, "edit_ops": ["SetTempo", "RenameTrack"], "native_export": "structural validation only", "native_reopen_verified": False},
    11: {"import": True, "inspect": True, "audio_preview": False, "edit_ops": ["SetTempo", "RenameTrack"], "native_export": "structural validation only", "native_reopen_verified": False},
    12: {"import": True, "inspect": True, "audio_preview": False, "edit_ops": ["SetTempo", "RenameTrack"], "native_export": "structural validation only", "native_reopen_verified": False},
}

KNOWN_DEVICES = {
    "Operator": ("Operator", "instrument"), "InstrumentVector": ("Wavetable", "instrument"), "OriginalSimpler": ("Simpler", "instrument"),
    "MultiSampler": ("Sampler", "instrument"), "Collision": ("Collision", "instrument"), "DrumGroupDevice": ("Drum Rack", "rack"),
    "InstrumentGroupDevice": ("Instrument Rack", "rack"), "AudioEffectGroupDevice": ("Audio Effect Rack", "rack"),
    "MidiEffectGroupDevice": ("MIDI Effect Rack", "rack"), "Compressor2": ("Compressor", "audio_effect"), "GlueCompressor": ("Glue Compressor", "audio_effect"),
    "Eq8": ("EQ Eight", "audio_effect"), "Reverb": ("Reverb", "audio_effect"), "Delay": ("Delay", "audio_effect"), "Echo": ("Echo", "audio_effect"),
    "AutoFilter": ("Auto Filter", "audio_effect"), "AutoPan": ("Auto Pan", "audio_effect"), "Saturator": ("Saturator", "audio_effect"),
    "Overdrive": ("Overdrive", "audio_effect"), "Erosion": ("Erosion", "audio_effect"), "DrumBuss": ("Drum Buss", "audio_effect"),
    "Limiter": ("Limiter", "audio_effect"), "Gate": ("Gate", "audio_effect"), "StereoGain": ("Utility", "audio_effect"),
    "BeatRepeat": ("Beat Repeat", "audio_effect"), "Redux2": ("Redux", "audio_effect"), "Tuner": ("Tuner", "audio_effect"),
    "MidiArpeggiator": ("Arpeggiator", "midi_effect"), "MidiScale": ("Scale", "midi_effect"), "MidiChord": ("Chord", "midi_effect"),
}
TRACK_TAGS = {"MidiTrack": "midi", "AudioTrack": "audio", "GroupTrack": "group", "ReturnTrack": "return"}


class AlsError(Exception):
    pass


def decode_container(data):
    if len(data) > MAX_COMPRESSED:
        raise AlsError(f"File is {len(data) / 1e6:.1f} MB; limit is {MAX_COMPRESSED // 2**20} MB")
    if data[:2] == b"\x1f\x8b":
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = bytearray()
        buf = data
        try:
            while buf:
                out += d.decompress(buf, 4 * 2**20)
                if len(out) > MAX_DECOMPRESSED:
                    raise AlsError("Decompressed size exceeds 200 MB safety limit (possible decompression bomb)")
                buf = d.unconsumed_tail
            out += d.flush()
        except zlib.error as e:
            raise AlsError(f"Malformed gzip stream: {e}")
        if not d.eof:
            raise AlsError("Truncated gzip stream (no end-of-stream marker)")
        return "gzip", bytes(out)
    head = data[:64].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<Ableton"):
        return "raw_xml", data
    if data[:4] == b"PK\x03\x04":
        raise AlsError("ZIP container detected (.alp pack?) - unsupported; extract it and import the .als")
    raise AlsError(f"Unknown container (magic bytes {data[:4].hex()}); not a gzip Live Set")


def parse_xml(xml):
    head = xml[:4096]
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise AlsError("DTD/entity declarations are not allowed in Live Sets (blocked for safety)")
    try:
        xml.decode("utf-8")
    except UnicodeDecodeError:
        raise AlsError("XML is not valid UTF-8")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, remove_blank_text=False)
    try:
        root = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError as e:
        raise AlsError(f"Malformed XML: {e}")
    if root.tag != "Ableton" or root.find("LiveSet") is None:
        raise AlsError("XML root is not <Ableton><LiveSet> - not a Live Set")
    return root


def _v(el, path, default=None):
    if el is None:
        return default
    x = el.find(path)
    return x.get("Value", default) if x is not None else default


def _f(el, path, default=None):
    v = _v(el, path)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def detect_version(root):
    creator = root.get("Creator", "")
    m = re.search(r"Live (\d+)\.(\d+)(?:\.(\d+))?", creator) or re.match(r"(\d+)\.(\d+)", root.get("MinorVersion", ""))
    major = int(m.group(1)) if m else None
    return {"creator": creator, "major": major, "minor_version": root.get("MinorVersion"), "schema_major": root.get("MajorVersion"),
            "adapter": f"live{major}" if major in COMPAT else "unknown", "capabilities": COMPAT.get(major, {"import": True, "inspect": True,
            "audio_preview": False, "edit_ops": [], "native_export": "blocked (unknown version)", "native_reopen_verified": False})}


def decode_timesig(v):
    v = int(v)
    return [v % 99 + 1, 2 ** (v // 99)]


def _devices(container):
    out = []
    if container is None:
        return out
    for d in container:
        if not isinstance(d.tag, str):
            continue
        name, kind = KNOWN_DEVICES.get(d.tag, (None, None))
        info = {"tag": d.tag, "name": name or d.tag, "kind": kind or "unknown", "known": name is not None,
                "on": _v(d, "On/Manual", "true") == "true", "line": d.sourceline,
                "preview_status": "Not renderable in browser (native Ableton device)"}
        if d.tag == "PluginDevice":
            info["plugin"] = _v(d, ".//PlugName") or _v(d, ".//Name")
            info["kind"] = "plugin"
            info["preview_status"] = "Not renderable (third-party plugin, opaque state preserved)"
        sc = d.find("SideChain")
        if sc is not None:
            info["sidechain"] = {"on": _v(sc, "OnOff/Manual") == "true", "target": _v(sc, "RoutedInput/Routable/Target")}
        params = {}
        for c in d:
            if isinstance(c.tag, str) and c.find("Manual") is not None and c.find("AutomationTarget") is not None:
                params[c.tag] = c.find("Manual").get("Value")
        info["parameters"] = params
        info["children"] = [x for br in d.findall("Branches/*") for devs in [br.find(".//Devices")] if devs is not None for x in _devices(devs)]
        out.append(info)
    return out


def _clip(c, scope):
    loop = c.find("Loop")
    cl = {"type": "midi" if c.tag == "MidiClip" else "audio", "scope": scope, "name": _v(c, "Name", ""),
          "start": _f(c, "CurrentStart", float(c.get("Time", 0))), "end": _f(c, "CurrentEnd", 0.0),
          "loop_start": _f(loop, "LoopStart"), "loop_end": _f(loop, "LoopEnd"), "loop_on": _v(loop, "LoopOn") == "true",
          "start_relative": _f(loop, "StartRelative"), "line": c.sourceline}
    if cl["type"] == "midi":
        notes = []
        for kt in c.findall("Notes/KeyTracks/KeyTrack"):
            key = int(_f(kt, "MidiKey", 60))
            for ne in kt.findall("Notes/MidiNoteEvent"):
                notes.append({"pitch": key, "time": float(ne.get("Time", 0)), "duration": float(ne.get("Duration", 0)),
                              "velocity": float(ne.get("Velocity", 0)), "probability": float(ne.get("Probability", 1)),
                              "enabled": ne.get("IsEnabled", "true") == "true", "id": ne.get("NoteId")})
        cl["note_count"] = len(notes)
        cl["notes"] = sorted(notes, key=lambda n: (n["time"], n["pitch"]))[:400]
        cl["clip_envelopes"] = len(c.findall("Envelopes/Envelopes/ClipEnvelope"))
    else:
        fr = c.find("SampleRef/FileRef")
        path = _v(fr, "Path") or _v(fr, "RelativePath")
        if path is None and fr is not None:  # Live 10 style
            parts = [e.get("Dir") for e in fr.findall("RelativePath/RelativePathElement")]
            path = "/".join([p for p in parts if p] + [_v(fr, "Name", "")])
        cl["sample"] = path
        cl["relative_path"] = _v(fr, "RelativePath")
    return cl


def analyze(xml_bytes, root=None):
    root = root if root is not None else parse_xml(xml_bytes)
    ver = detect_version(root)
    ls = root.find("LiveSet")
    masters = [x for x in ls if x.tag in ("MasterTrack", "MainTrack")]
    master = masters[0] if masters else None
    targets = {}
    dup_targets = []
    for el in root.iter("AutomationTarget", "ModulationTarget"):
        i = el.get("Id")
        if i in targets:
            dup_targets.append(i)
        par = el.getparent()
        dev = next((a.tag for a in par.iterancestors() if a.tag in KNOWN_DEVICES or a.tag == "PluginDevice"), None)
        targets[i] = {"param": par.tag, "device": dev}
    tempo_el = master.find("DeviceChain/Mixer/Tempo") if master is not None else None
    tempo = _f(tempo_el, "Manual")
    tempo_target = tempo_el.find("AutomationTarget").get("Id") if tempo_el is not None and tempo_el.find("AutomationTarget") is not None else None
    ts_raw = _v(master, "DeviceChain/Mixer/TimeSignature/Manual") if master is not None else None
    try:
        time_sig = decode_timesig(ts_raw) if ts_raw is not None else None
    except ValueError:
        time_sig = None

    def envelopes(el, owner):
        res = []
        for env in el.findall("AutomationEnvelopes/Envelopes/AutomationEnvelope"):
            pid = _v(env, "EnvelopeTarget/PointeeId")
            evs = [e for e in env.findall("Automation/Events/*")]
            pts = [{"time": float(e.get("Time", 0)), "value": e.get("Value")} for e in evs]
            res.append({"owner": owner, "pointee": pid, "resolved": pid in targets, "target": targets.get(pid),
                        "points": [p for p in pts if p["time"] != PREROLL][:200], "point_count": len(pts), "line": env.sourceline})
        return res

    tracks, all_env = [], []
    tracks_el = ls.find("Tracks")
    for el in (tracks_el if tracks_el is not None else []):
        if el.tag not in TRACK_TAGS:
            continue
        mixer = el.find("DeviceChain/Mixer")
        vol = _f(mixer, "Volume/Manual")
        seq = el.find("DeviceChain/MainSequencer")
        arr = seq.xpath(".//ArrangerAutomation/Events/MidiClip | .//ArrangerAutomation/Events/AudioClip") if seq is not None else []
        ses = seq.xpath("ClipSlotList//Value/MidiClip | ClipSlotList//Value/AudioClip") if seq is not None else []
        name = _v(el, "Name/EffectiveName") or _v(el, "Name/UserName") or el.tag
        envs = envelopes(el, name)
        all_env += envs
        tracks.append({
            "id": el.get("Id"), "kind": TRACK_TAGS[el.tag], "name": name, "color": _v(el, "Color", _v(el, "ColorIndex")),
            "group_id": _v(el, "TrackGroupId", "-1"), "line": el.sourceline,
            "name_line": el.find("Name/UserName").sourceline if el.find("Name/UserName") is not None else None,
            "volume_db": round(20 * math.log10(vol), 2) if vol and vol > 0 else None,
            "pan": _f(mixer, "Pan/Manual"), "active": _v(mixer, "Speaker/Manual", "true") == "true",
            "sends": [_f(s, "Send/Manual") for s in mixer.findall("Sends/TrackSendHolder")] if mixer is not None else [],
            "output": _v(el, "DeviceChain/AudioOutputRouting/Target"), "midi_input": _v(el, "DeviceChain/MidiInputRouting/Target"),
            "devices": _devices(el.find("DeviceChain/DeviceChain/Devices")),
            "clips": [_clip(c, "arrangement") for c in arr] + [_clip(c, "session") for c in ses],
            "take_lane_clips": len(el.xpath(".//TakeLanes//MidiClip | .//TakeLanes//AudioClip")),
            "envelopes": envs,
        })
    master_info = None
    if master is not None:
        menv = envelopes(master, "Master")
        all_env += menv
        master_info = {"tag": master.tag, "devices": _devices(master.find("DeviceChain/DeviceChain/Devices")), "envelopes": menv}
    tempo_auto = [e for e in (master_info or {}).get("envelopes", []) if e["pointee"] == tempo_target]
    tempo_points = [p for e in tempo_auto for p in e["points"]]
    # tree
    by_id = {t["id"]: t for t in tracks}
    for t in tracks:
        t["children"] = [c["id"] for c in tracks if c["group_id"] == t["id"]]
        depth, cur, seen = 0, t, set()
        while cur and cur["group_id"] not in ("-1", None) and cur["id"] not in seen:
            seen.add(cur["id"])
            cur = by_id.get(cur["group_id"])
            depth += 1
        t["depth"] = depth
    # sidechains
    sidechains = []
    for t in tracks + ([{"id": "master", "name": "Master", "devices": master_info["devices"]}] if master_info else []):
        def walk(devs):
            for d in devs:
                if "sidechain" in d:
                    tg = d["sidechain"]["target"] or ""
                    m = re.match(r"AudioIn/Track\.(\d+)", tg)
                    src = by_id.get(m.group(1)) if m else None
                    if not d["sidechain"]["on"]:
                        status = "inactive"
                    elif m and src:
                        status = "confirmed"
                    elif m:
                        status = "invalid"
                    elif tg.startswith("AudioIn/External"):
                        status = "confirmed_external"
                    else:
                        status = "inactive"
                    if d["sidechain"]["on"] or m:
                        sidechains.append({"destination": t["name"], "destination_id": t["id"], "device": d["name"], "route": tg,
                                           "source_id": m.group(1) if m else None, "source": src["name"] if src else None, "status": status})
                walk(d["children"])
        walk(t["devices"])
    assets = [{"track": t["name"], "clip": c["name"], "path": c["sample"],
               "status": "unresolved - referenced file not available to Parametric ALS (not embedded in .als)"}
              for t in tracks for c in t["clips"] if c["type"] == "audio"]
    clip_ends = [c["end"] for t in tracks for c in t["clips"] if c["scope"] == "arrangement" and c["end"]]
    transport = ls.find("Transport")
    scale = ls.find("ScaleInformation")
    elems = sum(1 for _ in root.iter())
    attrs = sum(len(e.attrib) for e in root.iter())
    known = {"Tracks", "MasterTrack", "MainTrack", "Transport", "Locators", "Scenes", "SceneNames", "NextPointeeId", "ScaleInformation"}
    unknown_top = [c.tag for c in ls if isinstance(c.tag, str) and c.tag not in known]
    summary = {
        "version": ver, "tempo": tempo, "tempo_automated": len({p["value"] for p in tempo_points}) > 1, "tempo_points": tempo_points,
        "time_signature": time_sig, "time_signature_raw": ts_raw,
        "key": {"root": _v(scale, "RootNote"), "scale": _v(scale, "Name")} if scale is not None else None,
        "loop": {"on": _v(transport, "LoopOn") == "true", "start": _f(transport, "LoopStart"), "length": _f(transport, "LoopLength")} if transport is not None else None,
        "locators": [{"time": _f(l, "Time"), "name": _v(l, "Name")} for l in ls.findall("Locators/Locators/Locator")],
        "scenes": [_v(s, "Name") for s in ls.findall("Scenes/Scene")] or [s.get("Value") for s in ls.findall("SceneNames/Scene")],
        "tracks": tracks, "master": master_info, "master_count": len(masters), "returns": sum(1 for t in tracks if t["kind"] == "return"),
        "sidechains": sidechains, "assets": assets, "arrangement_length_beats": max(clip_ends) if clip_ends else 0,
        "counts": {"tracks": len(tracks), "clips": sum(len(t["clips"]) for t in tracks), "notes": sum(c.get("note_count", 0) for t in tracks for c in t["clips"]),
                   "devices": sum(len(t["devices"]) for t in tracks), "envelopes": len(all_env), "elements": elems, "attributes": attrs},
        "unknown_top_level": unknown_top, "duplicate_automation_target_ids": sorted(set(dup_targets)),
        "tag_histogram_hash": hashlib.sha1(repr(sorted(Counter(e.tag for e in root.iter() if isinstance(e.tag, str)).items())).encode()).hexdigest(),
    }
    summary["invariants"] = invariants(summary, all_env, tracks)
    return summary


def _inv(i, title, ok, detail, fatal=True, na=False):
    return {"id": i, "title": title, "status": "n/a" if na else ("pass" if ok else ("fail" if fatal else "warn")), "fatal": fatal and not ok and not na, "detail": detail}


def invariants(s, envs, tracks):
    ids = [t["id"] for t in tracks]
    by_id = {t["id"] for t in tracks}
    cyc = any(t["depth"] > len(tracks) for t in tracks)
    bad_out = [t["name"] for t in tracks if t["output"] and re.match(r"AudioOut/Track\.(\d+)", t["output"]) and re.match(r"AudioOut/Track\.(\d+)", t["output"]).group(1) not in by_id]
    bad_grp = [t["name"] for t in tracks if t["group_id"] not in ("-1", None) and t["group_id"] not in by_id]
    bad_prefix = [t["name"] for t in tracks if t["output"] and not t["output"].startswith(("AudioOut", "MidiOut"))]
    bad_clips = [f"{t['name']}:{c['name']}" for t in tracks for c in t["clips"] if c["end"] is not None and c["start"] is not None and c["end"] < c["start"]]
    bad_notes = [f"{t['name']}:{c['name']}" for t in tracks for c in t["clips"] for n in c.get("notes", []) if n["duration"] <= 0 or not 0 <= n["pitch"] <= 127]
    bad_loops = [f"{t['name']}:{c['name']}" for t in tracks for c in t["clips"] if c["loop_start"] is not None and c["loop_end"] is not None and c["loop_end"] <= c["loop_start"]]
    nret = s["returns"]
    bad_sends = [t["name"] for t in tracks if len(t["sends"]) != nret]
    unresolved = [e["owner"] for e in envs if not e["resolved"]]
    bad_sc = [x["destination"] for x in s["sidechains"] if x["status"] == "invalid"]
    return [
        _inv("INV-001", "Tempo present and valid", s["tempo"] is not None and 20 <= s["tempo"] <= 999, f"Tempo = {s['tempo']}"),
        _inv("INV-002", "Time signature decodes", s["time_signature"] is not None, f"{s['time_signature']} (raw {s['time_signature_raw']})"),
        _inv("INV-003", "IDs unique in scope", len(ids) == len(set(ids)) and not s["duplicate_automation_target_ids"],
             f"{len(ids)} track ids; duplicate automation targets: {s['duplicate_automation_target_ids'] or 'none'}"),
        _inv("INV-004", "Automation targets resolve", not unresolved, f"Unresolved envelopes on: {unresolved or 'none'}"),
        _inv("INV-005", "Track hierarchy acyclic, parents exist", not cyc and not bad_grp, f"Missing parents: {bad_grp or 'none'}"),
        _inv("INV-006", "Routing endpoints exist", not bad_out, f"Broken outputs: {bad_out or 'none'}"),
        _inv("INV-007", "Routing types compatible", not bad_prefix, f"Unexpected output types: {bad_prefix or 'none'}", fatal=False),
        _inv("INV-008", "Sidechain references valid", not bad_sc, f"Invalid sidechains: {bad_sc or 'none'}"),
        _inv("INV-009", "Clip and note ranges valid", not bad_clips and not bad_notes, f"Bad clips: {bad_clips or 'none'}; bad notes: {bad_notes[:5] or 'none'}"),
        _inv("INV-010", "Return send topology consistent", not bad_sends, f"{nret} returns; mismatched: {bad_sends or 'none'}", fatal=False),
        _inv("INV-011", "New IDs do not collide", True, "No ID allocation by supported patch operations", na=True),
        _inv("INV-012", "UnknownSubtree preservation", True, f"Baseline: unknown top-level blocks {s['unknown_top_level'] or 'none'}; checked on export"),
        _inv("INV-013", "Residual attribute preservation", True, f"Baseline: {s['counts']['attributes']} attributes; checked on export"),
        _inv("INV-014", "Loop boundaries consistent", not bad_loops, f"Bad loops: {bad_loops or 'none'}"),
        _inv("INV-015", "Device order preserved", True, "Supported patch operations never reorder devices", na=True),
        _inv("INV-016", "Exactly one master track", s["master_count"] == 1, f"{s['master_count']} master/main track(s)"),
        _inv("INV-017", "Re-import semantically stable", True, "Evaluated on export", na=True),
    ]


def semantic_fingerprint(s):
    return {"tempo": s["tempo"], "time_signature": s["time_signature"],
            "tracks": [(t["id"], t["kind"], t["name"], t["group_id"], len(t["clips"]), sum(c.get("note_count", 0) for c in t["clips"]),
                        [d["tag"] for d in t["devices"]], t["output"], len(t["envelopes"])) for t in s["tracks"]],
            "sidechains": [(x["destination_id"], x["route"], x["status"]) for x in s["sidechains"]],
            "counts": s["counts"], "tags": s["tag_histogram_hash"], "unknown": s["unknown_top_level"]}


def _xml_attr(v):
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def compile_patch(original, ops):
    """Returns dict(report, data). Applies typed ops as single-attribute line patches."""
    container, xml = decode_container(original)
    root = parse_xml(xml)
    before = analyze(xml, root)
    ver = before["version"]
    report = {"operations": [], "diff": [], "status": "blocked", "native_reopen": "NOT VERIFIED - requires an Ableton Live installation; not available in this environment",
              "container": container, "source_version": ver["creator"]}
    if not ops:
        report.update(status="noop_identical", detail="No operations: original bytes returned unchanged (byte-identical).",
                      sha256_in=hashlib.sha256(original).hexdigest(), sha256_out=hashlib.sha256(original).hexdigest(),
                      invariants=before["invariants"])
        return {"report": report, "data": original}
    if ver["adapter"] == "unknown":
        report["error"] = "Unknown Live version - native export blocked"
        return {"report": report, "data": None}
    text = xml.decode("utf-8")
    lines = text.split("\n")
    expect = {"tempo": before["tempo"], "names": {}}

    def patch_line(ln, old, new, what):
        i = ln - 1
        needle = f'Value="{_xml_attr(old)}"'
        if lines[i].count(needle) != 1 or lines[i].count("<") != 1:
            raise AlsError(f"Cannot safely patch {what}: source line {ln} is not a single-element line")
        prev = lines[i]
        lines[i] = prev.replace(needle, f'Value="{_xml_attr(new)}"')
        report["diff"].append({"line": ln, "old": prev.strip(), "new": lines[i].strip(), "what": what})

    try:
        ls = root.find("LiveSet")
        master = next(x for x in ls if x.tag in ("MasterTrack", "MainTrack"))
        for op in ops:
            if op.get("type") not in ver["capabilities"]["edit_ops"]:
                raise AlsError(f"Operation {op.get('type')} is not supported for native .als patching")
            if op["type"] == "SetTempo":
                bpm = float(op["bpm"])
                if not 20 <= bpm <= 999:
                    raise AlsError("Tempo must be 20-999 BPM")
                if before["tempo_automated"]:
                    raise AlsError("Tempo is automated in this set; SetTempo would conflict with the tempo envelope")
                el = master.find("DeviceChain/Mixer/Tempo/Manual")
                newv = f"{bpm:g}"
                patch_line(el.sourceline, el.get("Value"), newv, "Tempo/Manual")
                tid = master.find("DeviceChain/Mixer/Tempo/AutomationTarget").get("Id")
                for env in master.findall("AutomationEnvelopes/Envelopes/AutomationEnvelope"):
                    if _v(env, "EnvelopeTarget/PointeeId") == tid:
                        for ev in env.findall("Automation/Events/FloatEvent"):
                            if float(ev.get("Time")) == PREROLL:
                                patch_line(ev.sourceline, ev.get("Value"), newv, "Tempo envelope pre-roll value")
                expect["tempo"] = float(newv)
            elif op["type"] == "RenameTrack":
                name = str(op["name"]).strip()
                if not name or len(name) > 64:
                    raise AlsError("Track name must be 1-64 characters")
                tr = next((t for t in ls.find("Tracks") if t.get("Id") == str(op["track_id"])), None)
                if tr is None:
                    raise AlsError(f"Track {op['track_id']} not found")
                for path in ("Name/EffectiveName", "Name/UserName"):
                    el = tr.find(path)
                    patch_line(el.sourceline, el.get("Value"), name, f"Track {op['track_id']} {path}")
                expect["names"][str(op["track_id"])] = name
            report["operations"].append(op)
    except (AlsError, StopIteration, KeyError, ValueError, AttributeError) as e:
        report["error"] = str(e) or "Unsupported structure"
        return {"report": report, "data": None}

    new_xml = "\n".join(lines).encode("utf-8")
    out = gzip.compress(new_xml, compresslevel=6, mtime=0) if container == "gzip" else new_xml
    # re-import verification
    c2, x2 = decode_container(out)
    after = analyze(x2)
    fp_b, fp_a = semantic_fingerprint(before), semantic_fingerprint(after)
    exp_tracks = [(t[0], t[1], expect["names"].get(t[0], t[2]), *t[3:]) for t in fp_b["tracks"]]
    unexpected = []
    if after["tempo"] != expect["tempo"]:
        unexpected.append("tempo")
    if fp_a["tracks"] != exp_tracks:
        unexpected.append("tracks/clips/devices")
    for k in ("time_signature", "sidechains", "counts", "tags", "unknown"):
        if fp_a[k] != fp_b[k]:
            unexpected.append(k)
    lines_changed = sum(1 for a, b in zip(xml.decode().split("\n"), lines) if a != b)
    inv = [dict(x) for x in after["invariants"]]
    for x in inv:
        if x["id"] == "INV-001":
            x["detail"] += f" (expected {expect['tempo']})"
            if after["tempo"] != expect["tempo"]:
                x.update(status="fail", fatal=True)
        if x["id"] == "INV-002" and fp_a["time_signature"] != fp_b["time_signature"]:
            x.update(status="fail", fatal=True)
        if x["id"] == "INV-012":
            ok = fp_a["unknown"] == fp_b["unknown"] and fp_a["tags"] == fp_b["tags"]
            x.update(status="pass" if ok else "fail", fatal=not ok, detail=f"Element tag histogram {'identical' if ok else 'CHANGED'}; unknown blocks {fp_a['unknown']}")
        if x["id"] == "INV-013":
            ok = after["counts"]["attributes"] == before["counts"]["attributes"]
            x.update(status="pass" if ok else "fail", fatal=not ok, detail=f"Attributes {before['counts']['attributes']} -> {after['counts']['attributes']}")
        if x["id"] == "INV-017":
            ok = not unexpected
            x.update(status="pass" if ok else "fail", fatal=not ok, detail="Re-imported output matches expected semantics" if ok else f"Unexpected changes: {unexpected}")
    gz_ok = c2 == container and x2 == new_xml
    fatal = [x["id"] for x in inv if x["fatal"]] + ([] if gz_ok else ["CONTAINER"])
    report.update(invariants=inv, lines_changed=lines_changed, gzip_roundtrip_ok=gz_ok, unexpected_changes=unexpected,
                  status="structurally_validated" if not fatal else "blocked", fatal=fatal,
                  unified_diff="\n".join(difflib.unified_diff(xml.decode().split("\n"), lines, "original.xml", "compiled.xml", n=1, lineterm=""))[:20000],
                  sha256_in=hashlib.sha256(original).hexdigest(), sha256_out=hashlib.sha256(out).hexdigest())
    return {"report": report, "data": out if not fatal else None}


def als_plans(s):
    """Manual-only recommendations for imported sets (no verified native device templates)."""
    out = []
    names = {t["name"].upper(): t for t in s["tracks"]}
    confirmed_dest = {x["destination_id"] for x in s["sidechains"] if x["status"].startswith("confirmed")}
    kick = next((t for t in s["tracks"] if "KICK" in t["name"].upper() and t["kind"] != "group"), None)
    for nm in ("BASS GROUP", "TEXTURE", "PAD", "RUMBLE", "BASS"):
        t = names.get(nm)
        if t and kick and t["id"] not in confirmed_dest and not (t["group_id"] in confirmed_dest):
            out.append({"id": f"als_sc_{t['id']}", "title": f"Sidechain {t['name']} from {kick['name']}", "kind": "sidechain",
                        "finding": f"No confirmed sidechain routing on {t['name']} (checked device SideChain routing, not names).",
                        "executable": False, "compatibility": "Manual only - native Compressor insertion has no verified template",
                        "confidence": 0.75, "manual_steps": [f"Track: {t['name']}", "Device: Compressor (last in chain)",
                        f"Sidechain ON, Audio From: {kick['name']} (Post FX)", "Ratio 4:1, Attack 0.1 ms, Release 120-160 ms, ~6 dB GR on hits",
                        "Verify: gain-reduction meter moves on every kick."]})
    if s["returns"] == 0:
        out.append({"id": "als_returns", "title": "Add reverb/delay returns", "kind": "structure", "finding": "Project has no return tracks.",
                    "executable": False, "compatibility": "Manual only", "confidence": 0.6,
                    "manual_steps": ["Create Return A with Reverb (Decay 3 s, Dry/Wet 100%)", "Create Return B with Echo (1/8 dotted, Feedback 45%)"]})
    if s["assets"]:
        out.append({"id": "als_assets", "title": f"Resolve {len(s['assets'])} referenced sample(s)", "kind": "assets",
                    "finding": "Audio clips reference files outside the .als.", "executable": False, "compatibility": "Manual only", "confidence": 1.0,
                    "manual_steps": ["In Live: File > Collect All and Save", "Re-export the set; keep the Samples folder alongside it."]})
    for t in s["tracks"]:
        if t["kind"] in ("midi", "audio") and not t["clips"]:
            out.append({"id": f"als_empty_{t['id']}", "title": f"{t['name']} has no clips", "kind": "unfinished",
                        "finding": "Track exists but contains no arrangement or session clips.", "executable": False,
                        "compatibility": "Manual only", "confidence": 0.9, "manual_steps": [f"Record or draw a clip on {t['name']}, or delete the track."]})
    if not any(e["points"] for t in s["tracks"] for e in t["envelopes"]):
        out.append({"id": "als_auto", "title": "No arrangement automation found", "kind": "automation",
                    "finding": "No track envelopes with points beyond pre-roll.", "executable": False, "compatibility": "Manual only", "confidence": 0.7,
                    "manual_steps": ["Automate a filter cutoff on the main synth across the breakdown (e.g. 400 Hz -> 8 kHz over 8 bars)."]})
    return out
