# Public-URL API regression tests for PARAMETRIC ALS (projects, ops, undo/redo, render, AI, ALS)
import gzip
import os
import struct

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
S = requests.Session()


def mk(template="berghain", seed=42):
    r = S.post(f"{API}/projects", json={"template": template, "seed": seed, "name": f"TEST_{template}"})
    assert r.status_code == 200, r.text
    return r.json()


def ops(p, oplist, rev=None):
    return S.post(f"{API}/projects/{p['id']}/ops", json={"base_revision": p["revision"] if rev is None else rev, "ops": oplist})


@pytest.fixture(scope="module")
def proj():
    p = mk()
    yield p
    S.delete(f"{API}/projects/{p['id']}")


def track_of(p, role):
    return next(t for t in p["tracks"] if t["role"] == role)


# --- Projects
@pytest.mark.parametrize("tpl", ["berghain", "tresor", "detroit", "empty"])
def test_create_templates(tpl):
    p = mk(tpl, 7)
    try:
        assert isinstance(p["tracks"], list)
        if tpl != "empty":
            assert len(p["tracks"]) >= 4
        g = S.get(f"{API}/projects/{p['id']}")
        assert g.status_code == 200 and g.json()["id"] == p["id"]
    finally:
        S.delete(f"{API}/projects/{p['id']}")


def test_deterministic_seed():
    a, b = mk("tresor", 1234), mk("tresor", 1234)
    try:
        pa = [t["pattern"] for t in a["tracks"]]
        pb = [t["pattern"] for t in b["tracks"]]
        assert pa == pb
    finally:
        for x in (a, b):
            S.delete(f"{API}/projects/{x['id']}")


def test_bad_template():
    assert S.post(f"{API}/projects", json={"template": "nope", "seed": 1}).status_code in (400, 422)


# --- Ops
def test_ops_batch_and_revision(proj):
    p = S.get(f"{API}/projects/{proj['id']}").json()
    k, h, st = track_of(p, "kick"), track_of(p, "hats"), track_of(p, "stabs")
    batch = [
        {"type": "ToggleStep", "track": k["id"], "index": 1},
        {"type": "UpdateStep", "track": k["id"], "index": 0, "fields": {"vel": 110, "ratchet": 2}},
        {"type": "SetTempo", "bpm": 133},
        {"type": "SetMacro", "index": 0, "value": 0.3},
        {"type": "ApplyMacroSnapshot", "name": "Tension Riser", "amount": 0.5},
        {"type": "SetSynthParam", "track": k["id"], "key": "pitch", "value": k["synth"]["pitch"]},
        {"type": "SetTrackParam", "track": h["id"], "key": "mute", "value": True},
        {"type": "SetTrackParam", "track": h["id"], "key": "solo", "value": False},
        {"type": "SetTrackParam", "track": h["id"], "key": "volume", "value": -6},
        {"type": "AddLayer", "role": "perc"},
        {"type": "ConfigureSidechain", "source": k["id"], "target": st["id"], "depth": 0.6},
        {"type": "SetAutomationLane", "target": "master.cutoff", "points": [{"bar": 0, "value": 500}, {"bar": 8, "value": 15000}]},
        {"type": "GenerateArrangementSection", "kind": "Breakdown", "bars": 8},
        {"type": "SetXY", "x": 0.2, "y": 0.8},
    ]
    r = ops(p, batch)
    assert r.status_code == 200, r.text
    q = r.json()["project"]
    assert q["revision"] == p["revision"] + 1
    assert q["bpm"] == 133
    assert track_of(q, "hats")["mute"] is True
    assert q["xy"] == {"x": 0.2, "y": 0.8}
    assert any(l["target"] == "master.cutoff" for l in q["automation"])
    assert any(s["name"] == "Breakdown" for s in q["sections"])
    g = S.get(f"{API}/projects/{p['id']}").json()
    assert g["revision"] == q["revision"] and g["bpm"] == 133


def test_record_performance(proj):
    p = S.get(f"{API}/projects/{proj['id']}").json()
    r = ops(p, [{"type": "RecordPerformance", "launches": [{"section": 0}, {"section": 0, "bars": 4}]}])
    assert r.status_code == 200, r.text
    secs = r.json()["project"]["sections"]
    assert len(secs) == 2 and secs[0]["origin"] == "performance"


def test_stale_revision_409(proj):
    p = S.get(f"{API}/projects/{proj['id']}").json()
    assert ops(p, [{"type": "SetTempo", "bpm": 130}], rev=p["revision"] - 1).status_code == 409


@pytest.mark.parametrize("op", [
    {"type": "SetTempo", "bpm": 500},
    {"type": "SetMacro", "index": 0, "value": 3},
    {"type": "Bogus"},
    {"type": "SetTrackParam", "track": "nope", "key": "mute", "value": True},
    {"type": "SetTempo"},
    {"type": "ToggleStep", "track": "x", "index": 0},
])
def test_invalid_ops_400(proj, op):
    p = S.get(f"{API}/projects/{proj['id']}").json()
    r = ops(p, [op])
    assert r.status_code == 400, r.text
    assert S.get(f"{API}/projects/{p['id']}").json()["revision"] == p["revision"]


def test_non_numeric_step_index_400(proj):
    # int("abc") -> ValueError is not caught by apply_ops (only KeyError/TypeError)
    p = S.get(f"{API}/projects/{proj['id']}").json()
    r = ops(p, [{"type": "ToggleStep", "track": p["tracks"][0]["id"], "index": "abc"}])
    assert r.status_code == 400, f"got {r.status_code}"


def test_undo_redo():
    p = mk("detroit", 9)
    try:
        r = ops(p, [{"type": "SetTempo", "bpm": 150}]).json()["project"]
        u = S.post(f"{API}/projects/{p['id']}/undo")
        assert u.status_code == 200 and u.json()["project"]["bpm"] == p["bpm"]
        d = S.post(f"{API}/projects/{p['id']}/redo")
        assert d.status_code == 200 and d.json()["project"]["bpm"] == 150
        assert S.post(f"{API}/projects/{p['id']}/redo").status_code == 400
        assert [t["pattern"] for t in d.json()["project"]["tracks"]] == [t["pattern"] for t in r["tracks"]]
    finally:
        S.delete(f"{API}/projects/{p['id']}")


def test_duplicate_and_list(proj):
    d = S.post(f"{API}/projects/{proj['id']}/duplicate")
    assert d.status_code == 200
    did = d.json()["id"]
    ids = [x["id"] for x in S.get(f"{API}/projects").json()]
    assert did in ids
    S.delete(f"{API}/projects/{did}")
    assert S.get(f"{API}/projects/{did}").status_code == 404


# --- Audio
def wav_hdr(b):
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE"
    return struct.unpack("<HHIIHH", b[20:36])


@pytest.mark.parametrize("mode,bits,sr", [("loop", 16, 44100), ("section", 24, 48000), ("arrangement", 32, 44100)])
def test_render_wav(proj, mode, bits, sr):
    q = f"mode={mode}&bits={bits}&sr={sr}" + ("&section=0" if mode == "section" else "") + ("&bars=4" if mode == "arrangement" else "")
    r = S.get(f"{API}/projects/{proj['id']}/render.wav?{q}", timeout=90)
    assert r.status_code == 200
    fmt, ch, rate, _, _, b = wav_hdr(r.content)
    assert rate == sr and b == bits and ch == 2


def test_render_track_repeat(proj):
    t = proj["tracks"][0]["id"]
    r = S.get(f"{API}/projects/{proj['id']}/render.wav?mode=loop&track={t}&repeat=16", timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"RIFF"


def test_render_bad_args(proj):
    assert S.get(f"{API}/projects/{proj['id']}/render.wav?bits=8").status_code == 400
    assert S.get(f"{API}/projects/{proj['id']}/render.wav?mode=foo").status_code == 400


def test_stats_and_macro_changes_audio():
    p = mk("berghain", 77)
    try:
        s1 = S.get(f"{API}/projects/{p['id']}/render/stats", timeout=60).json()
        assert "wav_header_check" in s1
        print(s1.keys())
        a1 = S.get(f"{API}/projects/{p['id']}/render.wav", timeout=60).content
        ops(p, [{"type": "SetMacro", "index": 0, "value": 1.0 if p["macros"][0] < 0.5 else 0.0}])
        a2 = S.get(f"{API}/projects/{p['id']}/render.wav", timeout=60).content
        assert a1 != a2
    finally:
        S.delete(f"{API}/projects/{p['id']}")


@pytest.mark.parametrize("v", ["kick", "hat_open", "stab_i", "rumble", "riser"])
def test_oneshot(proj, v):
    r = S.get(f"{API}/projects/{proj['id']}/oneshot/{v}.wav", timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"RIFF"


def test_oneshot_unknown(proj):
    assert S.get(f"{API}/projects/{proj['id']}/oneshot/zzz.wav").status_code == 404


def test_midi(proj):
    r = S.get(f"{API}/projects/{proj['id']}/midi.mid")
    assert r.status_code == 200 and r.content[:4] == b"MThd"


# --- AI
def test_analysis_preview_apply_explain():
    p = mk("berghain", 5)
    try:
        a = S.get(f"{API}/projects/{p['id']}/analysis?mode=Hybrid", timeout=60).json()
        assert a["plans"], "no plans"
        plan = a["plans"][0]
        assert plan["operations"] and all("type" in o for o in plan["operations"])
        pv = S.get(f"{API}/projects/{p['id']}/plans/{plan['id']}/preview.wav", timeout=90)
        assert pv.status_code == 200 and pv.content[:4] == b"RIFF"
        ap = S.post(f"{API}/projects/{p['id']}/plans/{plan['id']}/apply", json={"base_revision": p["revision"], "mode": "Hybrid"})
        assert ap.status_code == 200, ap.text
        assert ap.json()["project"]["revision"] == p["revision"] + 1
        st = S.post(f"{API}/projects/{p['id']}/plans/{plan['id']}/apply", json={"base_revision": p["revision"], "mode": "Hybrid"})
        assert st.status_code == 409
        assert S.post(f"{API}/ai/explain", json={"consent": False, "plan": plan}).status_code == 400
        ex = S.post(f"{API}/ai/explain", json={"consent": True, "plan": plan}, timeout=70)
        print("explain:", ex.status_code, ex.text[:300])
        assert ex.status_code == 200 and len(ex.json()["text"]) > 20
    finally:
        S.delete(f"{API}/projects/{p['id']}")


# --- ALS
@pytest.fixture(scope="module")
def demo():
    d = S.post(f"{API}/als/demo").json()
    yield d
    S.delete(f"{API}/als/{d['id']}")


def test_als_demo_summary(demo):
    s = demo["summary"]
    assert s["tempo"] == 140 and list(s["time_signature"]) == [4, 4]
    by = {t["name"]: t for t in s["tracks"]}
    assert by["KICK"]["group_id"] == by["DRUMS"]["id"] and by["HATS"]["group_id"] == by["DRUMS"]["id"]
    assert by["RUMBLE"]["group_id"] == by["BASS GROUP"]["id"]
    sc = s["sidechains"][0]
    assert sc["source"] == "KICK" and sc["destination"] == "BASS GROUP" and sc["status"] == "confirmed"
    assert "texture_loop.wav" in str(s["assets"]) and "unresolved" in str(s["assets"])
    assert "PluginDevice" in str(s["tracks"])
    assert [i["id"] for i in s["invariants"]] == [f"INV-{i:03d}" for i in range(1, 18)]


def test_als_import_garbage():
    r = S.post(f"{API}/als/import", files={"file": ("x.als", b"not an als file at all", "application/octet-stream")})
    assert r.status_code == 422


def test_als_import_real_bytes(demo):
    # Re-upload a no-op export of the fixture as a real file import
    c = S.post(f"{API}/als/{demo['id']}/compile", json={"ops": []}).json()
    data = S.get(f"{API}/als/exports/{c['id']}/download").content
    r = S.post(f"{API}/als/import", files={"file": ("TEST_fix.als", data, "application/octet-stream")})
    assert r.status_code == 200 and r.json()["summary"]["tempo"] == 140
    S.delete(f"{API}/als/{r.json()['id']}")


def test_als_compile_noop(demo):
    c = S.post(f"{API}/als/{demo['id']}/compile", json={"ops": []})
    assert c.status_code == 200 and c.json()["report"]["status"] == "noop_identical"


def test_als_compile_patch_download(demo):
    c = S.post(f"{API}/als/{demo['id']}/compile", json={"ops": [{"type": "SetTempo", "bpm": 136},
                                                                 {"type": "RenameTrack", "track_id": "15", "name": "PAD 2"}]})
    assert c.status_code == 200
    j = c.json()
    assert j["report"]["status"] == "structurally_validated", j["report"]
    assert j["downloadable"] is True
    d = S.get(f"{API}/als/exports/{j['id']}/download")
    assert d.status_code == 200 and d.content[:2] == b"\x1f\x8b"
    xml = gzip.decompress(d.content).decode("utf-8", "replace")
    assert "PAD 2" in xml and "136" in xml
    g = S.get(f"{API}/als/{demo['id']}").json()
    assert any(e["id"] == j["id"] for e in g["exports"])


def test_als_404():
    assert S.get(f"{API}/als/doesnotexist").status_code == 404
    assert S.get(f"{API}/als/exports/nope/download").status_code == 404


# --- Beat repeat regression: odd bar sample counts (e.g. 132 BPM) used to 500 with shape mismatch
@pytest.mark.parametrize("bpm", [128, 131, 132, 137])
@pytest.mark.parametrize("rep", [4, 8, 16, 32])
def test_beat_repeat_all_bpms(bpm, rep):
    p = mk("berghain", 11)
    try:
        ops(p, [{"type": "SetTempo", "bpm": bpm}])
        r = S.get(f"{API}/projects/{p['id']}/render.wav?mode=section&section=0&repeat={rep}", timeout=60)
        assert r.status_code == 200, f"bpm {bpm} repeat {rep}: {r.status_code}"
    finally:
        S.delete(f"{API}/projects/{p['id']}")
