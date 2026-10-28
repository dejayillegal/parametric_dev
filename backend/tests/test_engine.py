import copy
import gzip
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import als, composer as C, dsp, fixture, ops as OPS, planner  # noqa: E402


def test_timesig_decode():
    assert als.decode_timesig(201) == [4, 4]
    assert als.decode_timesig(200) == [3, 4]


def test_demo_als_parse_fidelity():
    s = als.analyze(fixture.build_demo_xml().encode())
    assert s["tempo"] == 140.0
    assert s["time_signature"] == [4, 4]
    names = {t["name"]: t for t in s["tracks"]}
    assert names["KICK"]["group_id"] == "10" and names["RUMBLE"]["group_id"] == "13"
    assert names["KICK"]["depth"] == 1
    assert len(names["KICK"]["clips"]) == 2 and names["KICK"]["clips"][0]["note_count"] == 64
    sc = [x for x in s["sidechains"] if x["status"] == "confirmed"]
    assert len(sc) == 1 and sc[0]["destination"] == "BASS GROUP" and sc[0]["source"] == "KICK"
    assert s["assets"] and s["assets"][0]["path"].endswith("texture_loop.wav")
    assert "ParametricUnknownFutureBlock" in s["unknown_top_level"]
    assert not [i for i in s["invariants"] if i["fatal"]]
    assert any(d["kind"] == "plugin" for d in names["MYSTERY SYNTH"]["devices"])


def test_noop_roundtrip_identical():
    data = fixture.build_demo_als()
    r = als.compile_patch(data, [])
    assert r["data"] == data and r["report"]["status"] == "noop_identical"


def test_settempo_patch_minimal():
    data = fixture.build_demo_als()
    r = als.compile_patch(data, [{"type": "SetTempo", "bpm": 136}, {"type": "RenameTrack", "track_id": "15", "name": "PAD & <X>"}])
    rep = r["report"]
    assert rep["status"] == "structurally_validated", rep
    assert rep["lines_changed"] == 4
    s2 = als.analyze(gzip.decompress(r["data"]))
    assert s2["tempo"] == 136.0
    assert any(t["name"] == "PAD & <X>" for t in s2["tracks"])


def test_reject_bad_containers():
    with pytest.raises(als.AlsError):
        als.decode_container(b"PK\x03\x04garbage")
    with pytest.raises(als.AlsError):
        als.decode_container(b"\x1f\x8b\x08\x00garbage")
    with pytest.raises(als.AlsError):
        als.parse_xml(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Ableton/>')


def test_seed_reproducible_and_varies():
    a = C.new_project("tresor", 7)
    b = C.new_project("tresor", 7)
    c = C.new_project("tresor", 8)
    assert a["tracks"] == b["tracks"]
    assert a["tracks"] != c["tracks"]


def test_kick_grid_locked():
    p = C.new_project("berghain", 3)
    k = next(t for t in p["tracks"] if t["role"] == "kick")
    assert all(s["micro"] == 0 for s in k["pattern"])


def test_ops_validation_and_preview_isolated():
    p = C.new_project("berghain", 1)
    with pytest.raises(OPS.OpError):
        OPS.apply_op(p, {"type": "SetTempo", "bpm": 500})
    q = OPS.preview(p, [{"type": "SetTempo", "bpm": 140}])
    assert q["bpm"] == 140 and p["bpm"] == 132


def test_wav_24bit_packing():
    x = np.array([[0.5, -0.5, 0.0], [1.0, -1.0, 0.25]], dtype=np.float32)
    b = dsp.encode_wav(x, 48000, 24, dither=False)
    h = dsp.parse_wav_header(b)
    assert h == {"format": 1, "channels": 2, "sr": 48000, "bits": 24, "frames": 3}
    first = int.from_bytes(b[44:47], "little", signed=True)
    assert first == round(0.5 * (2**23 - 1))
    neg = int.from_bytes(b[47:50], "little", signed=True)
    assert neg == round(1.0 * (2**23 - 1))


def test_render_audible_and_macro_changes_output():
    p = C.new_project("berghain", 1)
    p["id"] = "t"
    x, _ = dsp.render(p, bars=2)
    assert np.max(np.abs(x)) > 0.1 and np.all(np.isfinite(x))
    q = copy.deepcopy(p)
    q["macros"][0] = 1.0
    y, _ = dsp.render(q, bars=2)
    assert np.mean(np.abs(x - y)) > 1e-4


def test_mute_silences():
    p = C.new_project("berghain", 1)
    for t in p["tracks"]:
        t["mute"] = True
    x, _ = dsp.render(p, bars=1)
    assert np.max(np.abs(x)) < 1e-6


def test_planner_plans_are_executable():
    p = C.new_project("empty", 1)
    OPS.apply_op(p, {"type": "AddLayer", "role": "kick"})
    OPS.apply_op(p, {"type": "AddLayer", "role": "stabs"})
    res = planner.plans(p)
    assert res["plans"]
    for pl in res["plans"]:
        OPS.preview(p, pl["operations"])
