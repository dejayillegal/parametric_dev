from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import copy
import hashlib
import logging
import os
import struct
import time
import uuid

from bson import Binary

from engine import composer as C, dsp, ops as OPS, planner, als, fixture

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Parametric ALS API")
logger = logging.getLogger("parametric")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")
PROJ = {"_id": 0}


def now():
    return datetime.now(timezone.utc).isoformat()


def enrich(p):
    p["macro_display"] = dsp.macro_display(p["macros"])
    xy = dsp.xy_map(p["xy"])
    p["xy_display"] = {"cutoff": f"{xy['cutoff']:.0f} Hz", "drive": f"x{xy['drive']:.2f}"}
    return p


async def get_project(pid):
    p = await db.projects.find_one({"id": pid}, PROJ)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


async def save_project(p):
    p["updated_at"] = now()
    await db.projects.replace_one({"id": p["id"]}, p)


# ------------------------------------------------------------------ meta
@api.get("/")
async def root():
    return {"app": "Parametric ALS", "status": "ok"}


@api.get("/meta")
async def meta():
    return {"templates": {k: {"name": v["name"], "bpm": v["bpm"], "key": v["key"], "scale": v["scale"], "params": v["params"]} for k, v in C.TEMPLATES.items()},
            "keys": C.KEYS, "scales": list(C.SCALES), "rumble_presets": {k: v["name"] for k, v in C.RUMBLE_PRESETS.items()},
            "role_params": C.ROLE_PARAMS, "roles": {k: {"name": v[0], "group": v[1], "generator": v[3], "native_target": C.NATIVE_TARGETS[k]} for k, v in C.ROLE_META.items()},
            "macro_names": dsp.MACRO_NAMES, "snapshots": list(C.SNAPSHOTS) + ["Reset"], "automation_targets": dsp.AUTOMATION_TARGETS,
            "ai_modes": planner.MODES, "op_types": OPS.OP_TYPES, "als_compatibility": als.COMPAT}


# ------------------------------------------------------------------ projects
class NewProject(BaseModel):
    template: str = "berghain"
    seed: int = Field(default=1, ge=0, le=2**31)
    name: Optional[str] = None
    bpm: Optional[float] = Field(default=None, ge=60, le=200)
    key: Optional[str] = None
    scale: Optional[str] = None
    params: Optional[Dict[str, float]] = None
    length: int = Field(default=64, ge=16, le=256)


@api.post("/projects")
async def create_project(body: NewProject):
    if body.template not in list(C.TEMPLATES) + ["empty"]:
        raise HTTPException(400, "Unknown template")
    if body.key and body.key not in C.KEYS or body.scale and body.scale not in C.SCALES:
        raise HTTPException(400, "Unknown key/scale")
    for k, v in (body.params or {}).items():
        if k not in ("density", "tension", "groove", "distortion", "hypnotic", "width", "variation") or not 0 <= v <= 1:
            raise HTTPException(400, f"Invalid param {k}")
    p = C.new_project(body.template, body.seed, body.name, body.bpm, body.key, body.scale, body.params, body.length)
    p.update(id=str(uuid.uuid4()), created_at=now(), updated_at=now())
    await db.projects.insert_one(copy.deepcopy(p))
    return enrich(p)


@api.get("/projects")
async def list_projects():
    docs = await db.projects.find({}, {"_id": 0, "id": 1, "name": 1, "bpm": 1, "key": 1, "scale": 1, "template": 1, "seed": 1,
                                       "revision": 1, "updated_at": 1, "tracks.id": 1}).sort("updated_at", -1).to_list(200)
    for d in docs:
        d["track_count"] = len(d.pop("tracks", []))
    return docs


@api.get("/projects/{pid}")
async def read_project(pid: str):
    return enrich(await get_project(pid))


@api.delete("/projects/{pid}")
async def delete_project(pid: str):
    await get_project(pid)
    await db.projects.delete_one({"id": pid})
    await db.history.delete_many({"project_id": pid})
    await db.redo.delete_many({"project_id": pid})
    return {"deleted": pid}


@api.post("/projects/{pid}/duplicate")
async def duplicate_project(pid: str):
    p = await get_project(pid)
    p.update(id=str(uuid.uuid4()), name=f"{p['name']} copy", created_at=now(), updated_at=now(), revision=1)
    await db.projects.insert_one(copy.deepcopy(p))
    return enrich(p)


class OpRequest(BaseModel):
    base_revision: int
    ops: List[Dict[str, Any]]
    label: Optional[str] = None
    plan_id: Optional[str] = None


async def apply_ops(p, ops, label=None, plan_id=None):
    before = copy.deepcopy(p)
    descs = []
    try:
        for op in ops:
            descs.append(OPS.apply_op(p, op))
    except OPS.OpError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(400, f"Malformed operation: missing {e}")
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"Malformed operation: {e}")
    p["revision"] = before["revision"] + 1
    await db.history.insert_one({"project_id": p["id"], "revision": p["revision"], "ops": ops, "label": label or "; ".join(descs),
                                 "plan_id": plan_id, "before": before, "at": now()})
    await db.redo.delete_many({"project_id": p["id"]})
    await save_project(p)
    return descs


@api.post("/projects/{pid}/ops")
async def post_ops(pid: str, body: OpRequest):
    p = await get_project(pid)
    if body.base_revision != p["revision"]:
        raise HTTPException(409, f"Stale revision: project is at r{p['revision']}, request based on r{body.base_revision}")
    if not body.ops:
        raise HTTPException(400, "No operations")
    descs = await apply_ops(p, body.ops, body.label, body.plan_id)
    return {"project": enrich(p), "applied": descs}


@api.post("/projects/{pid}/undo")
async def undo(pid: str):
    p = await get_project(pid)
    h = await db.history.find_one({"project_id": pid}, sort=[("revision", -1)])
    if not h:
        raise HTTPException(400, "Nothing to undo")
    restored = h["before"]
    restored["revision"] = p["revision"] + 1
    await db.redo.insert_one({"project_id": pid, "seq": time.time(), "after": p, "label": h["label"], "ops": h["ops"], "plan_id": h.get("plan_id")})
    await db.history.delete_one({"_id": h["_id"]})
    await save_project(restored)
    return {"project": enrich(restored), "undone": h["label"]}


@api.post("/projects/{pid}/redo")
async def redo(pid: str):
    p = await get_project(pid)
    r = await db.redo.find_one({"project_id": pid}, sort=[("seq", -1)])
    if not r:
        raise HTTPException(400, "Nothing to redo")
    after = r["after"]
    after["revision"] = p["revision"] + 1
    await db.history.insert_one({"project_id": pid, "revision": after["revision"], "ops": r["ops"], "label": r["label"],
                                 "plan_id": r.get("plan_id"), "before": p, "at": now()})
    await db.redo.delete_one({"_id": r["_id"]})
    await save_project(after)
    return {"project": enrich(after), "redone": r["label"]}


@api.get("/projects/{pid}/history")
async def history(pid: str):
    h = await db.history.find({"project_id": pid}, {"_id": 0, "before": 0}).sort("revision", -1).to_list(100)
    r = await db.redo.count_documents({"project_id": pid})
    return {"history": h, "redo_available": r}


# ------------------------------------------------------------------ audio
_cache: "OrderedDict[str, Any]" = OrderedDict()


def _render_cached(p, mode, bars, section, mask, repeat, sr, track):
    key = hashlib.sha1(repr((p["id"], p["revision"], p.get("_preview"), mode, bars, section, mask, repeat, sr, track)).encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    t0 = time.time()
    x, info = dsp.render(p, mode=mode, bars=bars, section=section, mask=mask, repeat=repeat, sr=sr, solo_track=track,
                         loop_wrap=mode != "arrangement")
    info["render_ms"] = int((time.time() - t0) * 1000)
    _cache[key] = (x, info)
    while len(_cache) > 10:
        _cache.popitem(last=False)
    return x, info


def _render_args(mode, bars, section, mask, repeat, sr, bits):
    if mode not in ("loop", "section", "arrangement"):
        raise HTTPException(400, "mode must be loop|section|arrangement")
    if repeat not in (None, 4, 8, 16, 32):
        raise HTTPException(400, "repeat must be 4|8|16|32")
    if sr not in (44100, 48000):
        raise HTTPException(400, "sr must be 44100 or 48000")
    if bits not in (16, 24, 32):
        raise HTTPException(400, "bits must be 16, 24 or 32")
    return mask.split(",") if mask is not None else None


def _check_refs(p, mode, section, mask, track):
    ids = {t["id"] for t in p["tracks"]}
    if mode == "section" and (section is None or not 0 <= section < len(p["sections"])):
        raise HTTPException(400, f"section must be 0..{len(p['sections']) - 1}")
    if track is not None and track not in ids:
        raise HTTPException(400, f"Unknown track '{track}'")
    if mask is not None and any(m and m not in ids for m in mask):
        raise HTTPException(400, "mask contains unknown track ids")

@api.get("/projects/{pid}/render.wav")
async def render_wav(pid: str, mode: str = "loop", bars: int = Query(4, ge=1, le=256), section: Optional[int] = None,
                     mask: Optional[str] = None, repeat: Optional[int] = None, sr: int = 44100, bits: int = 16,
                     track: Optional[str] = None, normalize: bool = False, download: bool = False, rev: Optional[int] = None):
    p = await get_project(pid)
    m = _render_args(mode, bars, section, mask, repeat, sr, bits)
    _check_refs(p, mode, section, m, track)
    x, info = await asyncio.to_thread(_render_cached, p, mode, bars, section, m, repeat, sr, track)
    data = await asyncio.to_thread(dsp.encode_wav, x, sr, bits, bits != 32, normalize)
    fname = f"{p['name'].replace(' ', '_')}_{mode}{'_' + track if track else ''}_{bits}bit.wav"
    headers = {"X-Render-Ms": str(info["render_ms"]), "Cache-Control": "no-store"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return Response(data, media_type="audio/wav", headers=headers)


@api.get("/projects/{pid}/render/stats")
async def render_stats(pid: str, mode: str = "loop", bars: int = Query(4, ge=1, le=256), section: Optional[int] = None,
                       mask: Optional[str] = None, repeat: Optional[int] = None, sr: int = 44100, bits: int = 16, track: Optional[str] = None):
    p = await get_project(pid)
    m = _render_args(mode, bars, section, mask, repeat, sr, bits)
    _check_refs(p, mode, section, m, track)
    x, info = await asyncio.to_thread(_render_cached, p, mode, bars, section, m, repeat, sr, track)
    stats = await asyncio.to_thread(dsp.measure, x, sr)
    wav = dsp.encode_wav(x[:, :sr], sr, bits)
    return {**info, **stats, "sr": sr, "bits": bits, "frames": x.shape[1], "revision": p["revision"],
            "wav_header_check": dsp.parse_wav_header(wav)}


ONESHOTS = ["kick", "rumble", "perc_lo", "perc_hi", "hat_closed", "hat_open", "stab_i", "stab_iv", "stab_vi", "stab_v",
            "sub_root", "sub_fifth", "riser", "impact", "noise_hit", "rim"]


def oneshot(p, voice, sr=44100):
    tr = {t["role"]: t for t in p["tracks"]}
    syn = lambda r: (tr[r]["synth"] if r in tr else C.default_synth(r))
    m = dsp.macro_map(p["macros"])
    root3 = C.root_midi(p["key"], 3)
    sc = C.SCALES[p["scale"]]
    import numpy as np
    k = syn("kick")
    if voice == "kick":
        y = dsp.kick_voice(sr, k["pitch"], k["depth"], k["pitch_decay"], k["amp_decay"], k["click"], k["saturation"])
    elif voice in ("rumble", "sub_root", "sub_fifth"):
        r = syn("rumble")
        y = dsp.sub_voice(sr, C.root_midi(p["key"], 1) + (7 if voice == "sub_fifth" else 0), 0.4, r["sub_decay"] * (3 if voice == "rumble" else 1), r["saturation"]).copy()
        if voice == "rumble":
            kv = dsp.kick_voice(sr, k["pitch"], k["depth"], k["pitch_decay"], k["amp_decay"], 0.0, 1.0)
            ir = dsp.reverb_ir(sr, round(m["rumble_decay"], 2), 5)[0]
            from scipy import signal
            rum = signal.fftconvolve(kv, ir)
            rum = signal.sosfilt(dsp._sos("lowpass", m["sub_cutoff"], sr, 4), rum)
            y = np.pad(y, (0, len(rum) - len(y))) * 0.6 + np.tanh(rum * 2) * 0.6
    elif voice.startswith("perc") or voice == "rim":
        pr = syn("perc")
        f = pr["freq"] * {"perc_lo": 1, "perc_hi": 1.5, "rim": 2.4}[voice]
        y = dsp.metal_voice(sr, round(f, 1), pr["ratio"], pr["index"], pr["decay"], round(m["drive"], 2))
    elif voice.startswith("hat"):
        h = syn("hats")
        y = dsp.hat_voice(sr, round((h["open_decay"] if voice == "hat_open" else h["closed_decay"]) * m["hat_decay"], 3), h["tone"])
    elif voice.startswith("stab"):
        s = syn("stabs")
        deg = {"stab_i": 0, "stab_iv": 3, "stab_vi": 5, "stab_v": 4}[voice]
        y = dsp.stab_voice(sr, tuple(root3 + sc[deg] + iv for iv in (0, 3, 7)), 0.3, s["cutoff"], s["env_amt"], s["detune"])
    elif voice in ("riser", "noise_hit", "impact"):
        dur = {"riser": 60 / p["bpm"] * 8, "noise_hit": 0.6, "impact": 2.5}[voice]
        n = int(sr * dur)
        t = np.arange(n) / sr
        nz = dsp._noise(n, 3)
        if voice == "riser":
            y = dsp.tv_filter(nz * (t / dur) ** 2, sr, 300 * (40 ** (t / dur)), "highpass") * 0.5
        elif voice == "noise_hit":
            y = nz * np.exp(-t / 0.12) * 0.5
        else:
            kv = dsp.kick_voice(sr, 45.0, 120.0, 0.06, 0.9, 1.0, 3.0)
            y = np.pad(kv, (0, max(0, n - len(kv))))[:n] + nz * np.exp(-t / 0.5) * 0.25
    else:
        raise HTTPException(404, "Unknown voice")
    st = np.stack([y, y]).astype(np.float32) * 0.8
    st, _ = dsp.limiter(st, sr)
    return dsp.encode_wav(st, sr, 16)


@api.get("/projects/{pid}/oneshot/{voice}.wav")
async def oneshot_wav(pid: str, voice: str, rev: Optional[int] = None):
    if voice not in ONESHOTS:
        raise HTTPException(404, "Unknown voice")
    p = await get_project(pid)
    data = await asyncio.to_thread(oneshot, p, voice)
    return Response(data, media_type="audio/wav")


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def build_midi(p, bars):
    """Standard MIDI File type 1, 480 PPQ. Pattern steps -> notes (microtiming kept in ticks)."""
    ppq = 480
    st = ppq // 4
    trks = []
    tempo = int(60_000_000 / p["bpm"])
    trks.append(b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big") + b"\x00\xff\x58\x04\x04\x02\x18\x08" + b"\x00\xff\x2f\x00")
    drum = {"kick": 36, "perc": None, "hats": None}
    for ch_i, t in enumerate(p["tracks"]):
        ch = 9 if t["role"] in ("kick", "hats", "perc") else min(8, ch_i)
        evs = []
        L = len(t["pattern"])
        for g in range(bars * 16):
            s = t["pattern"][g % L]
            if not s["on"]:
                continue
            tick = max(0, g * st + int(round(s.get("micro", 0) / 1000 * p["bpm"] / 60 * ppq)))
            dur = max(1, int(st * s.get("gate", 1)))
            pitches = [drum["kick"]] if t["role"] == "kick" else [s.get("pitch", 60) + iv for iv in s.get("chord", [0])]
            for pt in pitches:
                evs.append((tick, 1, 0x90 | ch, pt, int(s.get("vel", 100))))
                evs.append((tick + dur, 0, 0x80 | ch, pt, 0))
        evs.sort(key=lambda e: (e[0], e[1]))
        name = t["name"].encode()[:60]
        body = b"\x00\xff\x03" + _vlq(len(name)) + name
        last = 0
        for tick, _, status, pt, vel in evs:
            body += _vlq(tick - last) + bytes([status, pt & 0x7F, vel & 0x7F])
            last = tick
        body += b"\x00\xff\x2f\x00"
        trks.append(body)
    out = b"MThd" + struct.pack(">IHHH", 6, 1, len(trks), ppq)
    for b in trks:
        out += b"MTrk" + struct.pack(">I", len(b)) + b
    return out


@api.get("/projects/{pid}/midi.mid")
async def midi(pid: str, bars: int = Query(16, ge=1, le=256)):
    p = await get_project(pid)
    return Response(build_midi(p, bars), media_type="audio/midi",
                    headers={"Content-Disposition": f'attachment; filename="{p["name"].replace(" ", "_")}.mid"'})


# ------------------------------------------------------------------ AI
@api.get("/projects/{pid}/analysis")
async def analysis(pid: str, mode: str = "Hybrid"):
    p = await get_project(pid)
    res = planner.plans(p, mode)
    applied = await db.history.find({"project_id": pid, "plan_id": {"$ne": None}}, {"_id": 0, "plan_id": 1, "label": 1, "revision": 1}).to_list(100)
    res["applied_plans"] = applied
    return res


async def _find_plan(p, plan_id, mode):
    plan = next((x for x in planner.plans(p, mode)["plans"] if x["id"] == plan_id), None)
    if not plan:
        raise HTTPException(409, "Plan not valid for the current project revision; re-run analysis")
    return plan


@api.get("/projects/{pid}/plans/{plan_id}/preview.wav")
async def plan_preview(pid: str, plan_id: str, mode: str = "Hybrid", original: bool = False):
    p = await get_project(pid)
    plan = await _find_plan(p, plan_id, mode)
    q = p if original else OPS.preview(p, plan["operations"])
    if not original:
        q["_preview"] = plan_id
    secs = q["sections"]
    sec = None
    acc = 0
    for i, s in enumerate(secs):
        if acc <= plan["start_bar"] < acc + s["bars"]:
            sec = i
            break
        acc += s["bars"]
    x, _ = await asyncio.to_thread(_render_cached, q, "section" if sec is not None else "loop", 4, sec, None, None, 44100, None)
    return Response(dsp.encode_wav(x, 44100, 16), media_type="audio/wav")


class ApplyPlan(BaseModel):
    base_revision: int
    mode: str = "Hybrid"


@api.post("/projects/{pid}/plans/{plan_id}/apply")
async def plan_apply(pid: str, plan_id: str, body: ApplyPlan):
    p = await get_project(pid)
    if body.base_revision != p["revision"]:
        raise HTTPException(409, "Stale revision; re-run analysis")
    plan = await _find_plan(p, plan_id, body.mode)
    descs = await apply_ops(p, plan["operations"], f"AI: {plan['title']}", plan_id)
    return {"project": enrich(p), "applied": descs}


class ExplainReq(BaseModel):
    consent: bool
    plan: Dict[str, Any]


@api.post("/ai/explain")
async def explain(body: ExplainReq):
    if not body.consent:
        raise HTTPException(400, "Cloud explanation requires explicit consent")
    ctx = planner.explain_context(body.plan)
    cache_key = hashlib.sha1(ctx.encode()).hexdigest()
    hit = await db.explanations.find_one({"key": cache_key}, {"_id": 0})
    if hit:
        return {"text": hit["text"], "cached": True, "model": hit["model"]}
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "Cloud AI not configured; rule-based rationale still available")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    model = "claude-sonnet-5-5"
    chat = LlmChat(api_key=key, session_id=f"explain-{cache_key}",
                   system_message="You are a techno mix engineer. Explain the given typed DAW operation plan to a producer in 3-4 short sentences: what changes, why it helps the groove/mix, what to listen for. Do not invent values not in the plan. No markdown.").with_model("anthropic", model)
    text = ""
    try:
        async def run():
            nonlocal text
            async for ev in chat.stream_message(UserMessage(text=ctx)):
                if isinstance(ev, TextDelta):
                    text += ev.content
                elif isinstance(ev, StreamDone):
                    break
        await asyncio.wait_for(run(), timeout=45)
    except Exception as e:  # noqa: BLE001 - surface as degraded state, never fake text
        logger.warning("explain failed: %s", e)
        raise HTTPException(503, f"Cloud AI unavailable ({type(e).__name__}); rule-based rationale still available")
    await db.explanations.insert_one({"key": cache_key, "text": text.strip(), "model": model, "at": now()})
    return {"text": text.strip(), "cached": False, "model": model}


# ------------------------------------------------------------------ ALS
async def _store_als(filename, data):
    try:
        container, xml = als.decode_container(data)
        summary = await asyncio.to_thread(als.analyze, xml)
    except als.AlsError as e:
        raise HTTPException(422, str(e))
    sid = str(uuid.uuid4())
    sha = hashlib.sha256(data).hexdigest()
    await db.als_blobs.insert_one({"id": sid, "data": Binary(data)})
    doc = {"id": sid, "filename": filename, "sha256": sha, "size": len(data), "container": container, "summary": summary,
           "created_at": now(), "plans": als.als_plans(summary)}
    await db.als_sets.insert_one(copy.deepcopy(doc))
    return doc


@api.post("/als/import")
async def als_import(file: UploadFile = File(...)):
    name = os.path.basename(file.filename or "upload.als")[:120]
    data = await file.read(als.MAX_COMPRESSED + 1)
    return await _store_als(name, data)


@api.post("/als/demo")
async def als_demo():
    return await _store_als("parametric_synthetic_fixture_live11.als", fixture.build_demo_als())


@api.get("/als")
async def als_list():
    docs = await db.als_sets.find({}, {"_id": 0, "id": 1, "filename": 1, "size": 1, "created_at": 1, "summary.tempo": 1,
                                       "summary.version.creator": 1, "summary.counts": 1}).sort("created_at", -1).to_list(100)
    return docs


@api.get("/als/{sid}")
async def als_get(sid: str):
    d = await db.als_sets.find_one({"id": sid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Live Set not found")
    d["exports"] = await db.als_exports.find({"set_id": sid}, {"_id": 0, "data": 0}).sort("created_at", -1).to_list(20)
    return d


@api.delete("/als/{sid}")
async def als_delete(sid: str):
    await db.als_sets.delete_one({"id": sid})
    await db.als_blobs.delete_one({"id": sid})
    await db.als_exports.delete_many({"set_id": sid})
    return {"deleted": sid}


class CompileReq(BaseModel):
    ops: List[Dict[str, Any]] = []


@api.post("/als/{sid}/compile")
async def als_compile(sid: str, body: CompileReq):
    d = await db.als_sets.find_one({"id": sid}, {"_id": 0, "filename": 1})
    blob = await db.als_blobs.find_one({"id": sid})
    if not d or not blob:
        raise HTTPException(404, "Live Set not found")
    res = await asyncio.to_thread(als.compile_patch, bytes(blob["data"]), body.ops)
    eid = str(uuid.uuid4())
    rec = {"id": eid, "set_id": sid, "created_at": now(), "report": res["report"], "downloadable": res["data"] is not None,
           "filename": d["filename"].replace(".als", "") + ("_noop.als" if not body.ops else "_parametric.als")}
    store = dict(rec)
    if res["data"] is not None:
        store["data"] = Binary(res["data"])
    await db.als_exports.insert_one(store)
    return rec


@api.get("/als/exports/{eid}/download")
async def als_download(eid: str):
    e = await db.als_exports.find_one({"id": eid})
    if not e or not e.get("data"):
        raise HTTPException(404, "No validated export available (blocked or missing)")
    return Response(bytes(e["data"]), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{e["filename"]}"'})


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Render-Ms"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
