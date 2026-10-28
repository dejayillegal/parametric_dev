"""Parametric ALS offline DSP engine (numpy/scipy).

Deterministic: the same project revision + render parameters always yields the
same samples. All instruments are original synthesis (no samples embedded).
"""
import hashlib
import math
import struct
from functools import lru_cache

import numpy as np
from scipy import signal

MACRO_NAMES = ["Sub Cutoff", "Rumble Decay", "Industrial Drive", "Hypnotic Echo",
               "Hat Decay", "Master Crush", "Reverb Send", "Delay Feedback"]

AUTOMATION_TARGETS = {
    "master.cutoff": {"unit": "Hz", "min": 200.0, "max": 20000.0},
    "stabs.cutoff": {"unit": "Hz", "min": 200.0, "max": 12000.0},
    "rumble.cutoff": {"unit": "Hz", "min": 40.0, "max": 600.0},
    "master.volume": {"unit": "dB", "min": -36.0, "max": 0.0},
}


def macro_map(m):
    return {
        "sub_cutoff": 40.0 * (10 ** m[0]),
        "rumble_decay": 0.15 + 1.35 * m[1],
        "drive": 1.0 + 11.0 * m[2],
        "echo_mix": 0.6 * m[3],
        "hat_decay": 0.3 + 1.7 * m[4],
        "crush_bits": None if m[5] < 0.02 else 16.0 - 12.0 * m[5],
        "reverb_send": 0.6 * m[6],
        "delay_fb": 0.85 * m[7],
    }


def macro_display(m):
    v = macro_map(m)
    return [f"{v['sub_cutoff']:.0f} Hz", f"{v['rumble_decay']:.2f} s",
            f"+{20 * math.log10(v['drive']):.1f} dB", f"{v['echo_mix'] * 100:.0f}% wet",
            f"x{v['hat_decay']:.2f}", "Off" if v["crush_bits"] is None else f"{v['crush_bits']:.1f} bit",
            f"{v['reverb_send'] * 100:.0f}%", f"{v['delay_fb'] * 100:.0f}%"]


def xy_map(xy):
    return {"cutoff": 200.0 * (100 ** xy["x"]), "drive": 1.0 + 7.0 * xy["y"]}


def m2f(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def _sos(kind, fc, sr, order=2):
    fc = float(min(max(fc, 10.0), sr * 0.45))
    return signal.butter(order, fc, kind, fs=sr, output="sos")


# ---------------------------------------------------------------- voices
@lru_cache(maxsize=256)
def kick_voice(sr, pitch, depth, pdecay, adecay, click, sat):
    n = int(sr * min(1.2, adecay * 5 + 0.05))
    t = np.arange(n) / sr
    f = pitch + depth * np.exp(-t / pdecay)
    y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / adecay)
    y *= np.minimum(1.0, t / 0.0008)
    y += click * 0.6 * _noise(n, 909) * np.exp(-t / 0.0025)
    return (np.tanh(sat * y) / np.tanh(sat)).astype(np.float32)


@lru_cache(maxsize=512)
def sub_voice(sr, midi, dur, decay, sat):
    n = int(sr * (dur + 0.05))
    t = np.arange(n) / sr
    env = np.minimum(1.0, t / 0.004) * np.exp(-t / decay)
    env *= np.clip((dur + 0.03 - t) / 0.03, 0, 1)
    y = np.sin(2 * np.pi * m2f(midi) * t) * env
    return (np.tanh(sat * y) / np.tanh(sat)).astype(np.float32)


@lru_cache(maxsize=256)
def metal_voice(sr, freq, ratio, index, decay, drive):
    n = int(sr * min(1.5, decay * 6 + 0.02))
    t = np.arange(n) / sr
    mod = np.sin(2 * np.pi * freq * ratio * t) * index * np.exp(-t / (decay * 0.5))
    car = np.sin(2 * np.pi * freq * t + mod)
    ring = car * np.sin(2 * np.pi * freq * 2.76 * t)
    y = (0.6 * car + 0.4 * ring) * np.exp(-t / decay) + 0.3 * _noise(n, 77) * np.exp(-t / 0.01)
    y = signal.sosfilt(signal.butter(2, [250, min(9000, sr * 0.45)], "bandpass", fs=sr, output="sos"), y)
    return (np.tanh(drive * y) / np.tanh(drive) * 0.8).astype(np.float32)


@lru_cache(maxsize=64)
def hat_voice(sr, decay, tone):
    n = int(sr * min(1.5, decay * 6 + 0.02))
    t = np.arange(n) / sr
    sq = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)) / 6
    y = 0.55 * sq + 0.45 * _noise(n, 808)
    y = signal.sosfilt(_sos("highpass", tone, sr, 4), y) * np.exp(-t / decay)
    return (y * 0.7).astype(np.float32)


@lru_cache(maxsize=256)
def stab_voice(sr, notes, dur, cutoff, env_amt, detune):
    n = int(sr * (dur + 0.35))
    t = np.arange(n) / sr
    y = np.zeros(n)
    for i, m in enumerate(notes):
        for j, d in enumerate((-detune, 0.0, detune)):
            ff = m2f(m) * 2 ** (d / 1200.0)
            y += 2 * ((ff * t + 0.37 * (i + j)) % 1.0) - 1
    y /= max(1, len(notes) * 3)
    amp = np.minimum(1.0, t / 0.004) * np.exp(-t / (dur * 0.6 + 0.08)) * np.clip((dur + 0.3 - t) / 0.3, 0, 1)
    dark = signal.sosfilt(_sos("lowpass", cutoff, sr), y)
    bright = signal.sosfilt(_sos("lowpass", cutoff * (1 + 4 * env_amt), sr), y)
    fe = np.exp(-t / 0.07)
    return ((bright * fe + dark * (1 - fe)) * amp * 0.9).astype(np.float32)


@lru_cache(maxsize=8)
def reverb_ir(sr, seconds, seed=11):
    n = int(sr * seconds)
    t = np.arange(n) / sr
    env = np.exp(-t * 6.9 / seconds)
    ir = np.stack([_noise(n, seed) * env, _noise(n, seed + 1) * env])
    ir = signal.sosfilt(_sos("lowpass", 6000, sr), ir, axis=1)
    return (ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))).astype(np.float32)


# ---------------------------------------------------------------- helpers
def _place(buf, start, v, gain):
    if gain <= 0 or start >= len(buf):
        return
    end = min(len(buf), start + len(v))
    buf[start:end] += v[: end - start] * gain


def tv_filter(x, sr, fc, kind="lowpass", block=1024):
    """Time-varying 2-pole filter. fc: per-sample cutoff array (Hz)."""
    out = np.empty_like(x)
    zi = np.zeros((1, 2))
    for s in range(0, len(x), block):
        sos = _sos(kind, float(fc[s]), sr)
        out[s:s + block], zi = signal.sosfilt(sos, x[s:s + block], zi=zi)
    return out


def lane_values(lane, bars):
    pts = sorted(lane["points"], key=lambda p: p["bar"])
    if not pts:
        return None
    xs = np.array([p["bar"] for p in pts], dtype=float)
    ys = np.array([p["value"] for p in pts], dtype=float)
    curve = lane.get("curve", "linear")
    if curve == "step":
        idx = np.clip(np.searchsorted(xs, bars, side="right") - 1, 0, len(ys) - 1)
        return ys[idx]
    if curve == "exp" and np.all(ys > 0):
        return np.exp(np.interp(bars, xs, np.log(ys)))
    v = np.interp(bars, xs, ys)
    if curve == "s":
        i = np.clip(np.searchsorted(xs, bars, side="right") - 1, 0, len(xs) - 2) if len(xs) > 1 else np.zeros_like(bars, dtype=int)
        if len(xs) > 1:
            span = np.maximum(xs[i + 1] - xs[i], 1e-9)
            u = np.clip((bars - xs[i]) / span, 0, 1)
            u = u * u * (3 - 2 * u)
            v = ys[i] + (ys[i + 1] - ys[i]) * u
    return v


def hit_rand(seed, tid, g):
    h = hashlib.blake2b(f"{seed}:{tid}:{g}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2 ** 64


def track_events(project, track, g0, nsteps, sd, active_bar):
    pat = track["pattern"]
    L = len(pat)
    swing = project["params"]["groove"] * 0.33
    out = []
    if L == 0:
        return out
    for g in range(g0, g0 + nsteps):
        if not active_bar((g - g0) // 16):
            continue
        st = pat[g % L]
        if not st.get("on"):
            continue
        if st.get("prob", 1.0) < 1.0 and hit_rand(project["seed"], track["id"], g) > st["prob"]:
            continue
        base = (g - g0) * sd
        if track["role"] != "kick":
            base += (swing * sd if g % 2 == 1 else 0.0) + st.get("micro", 0.0) / 1000.0
        r = max(1, int(st.get("ratchet", 1)))
        for k in range(r):
            out.append((max(0.0, base + k * sd / r), st, st.get("vel", 100) / 127.0 * (1 - 0.18 * k)))
    return out


# ---------------------------------------------------------------- render
def render(project, mode="loop", bars=4, section=None, mask=None, repeat=None,
           sr=44100, solo_track=None, loop_wrap=True):
    """Returns (stereo float32 array shape (2, n), info dict)."""
    bpm = float(project["bpm"])
    sd = 60.0 / bpm / 4
    m = macro_map(project["macros"])
    xy = xy_map(project.get("xy", {"x": 1.0, "y": 0.0}))
    p = project["params"]
    tracks = project["tracks"]
    sections = project.get("sections", [])

    # timeline: which bars, which tracks active per bar, automation bar offset
    if mode == "arrangement" and sections:
        total = sum(s["bars"] for s in sections)
        bar_map = []
        for s in sections:
            bar_map += [set(s["active"])] * s["bars"]
        bar_offset = 0
    elif mode == "section" and section is not None and 0 <= section < len(sections):
        s = sections[section]
        total = s["bars"] if bars is None else bars
        bar_map = [set(s["active"])] * total
        bar_offset = sum(x["bars"] for x in sections[:section])
    else:
        total = bars or 4
        bar_map = [set(mask) if mask is not None else {t["id"] for t in tracks}] * total
        bar_offset = 0
    nsteps = total * 16
    length = int(round(nsteps * sd * sr))
    tail = int(sr * 2.5)
    n = length + tail
    bar_axis = bar_offset + np.arange(n) / sr / (sd * 16)

    any_solo = any(t.get("solo") for t in tracks)

    def audible(t):
        if solo_track:
            return t["id"] == solo_track
        return not t.get("mute") and (not any_solo or t.get("solo"))

    kick_t = next((t for t in tracks if t["role"] == "kick"), None)
    kick_times = []
    if kick_t:
        kick_times = [e[0] for e in track_events(project, kick_t, 0, nsteps, sd,
                                                  lambda b: kick_t["id"] in bar_map[b])]

    master = np.zeros((2, n), dtype=np.float32)
    rev_bus = np.zeros((2, n), dtype=np.float32)
    lanes = {ln["target"]: ln for ln in project.get("automation", []) if ln.get("enabled", True)}

    for t in tracks:
        if not audible(t):
            continue
        tid, role, sp = t["id"], t["role"], t["synth"]
        ev = track_events(project, t, 0, nsteps, sd, lambda b, tid=tid: tid in bar_map[b])
        mono = np.zeros(n, dtype=np.float32)
        stereo = None
        if role == "kick":
            v = kick_voice(sr, sp["pitch"], sp["depth"], sp["pitch_decay"], sp["amp_decay"], sp["click"], sp["saturation"])
            for tm, st, g in ev:
                _place(mono, int(tm * sr), v, g)
        elif role == "rumble":
            for tm, st, g in ev:
                v = sub_voice(sr, int(st.get("pitch", 29)), round(st.get("gate", 1) * sd, 4), sp["sub_decay"], sp["saturation"])
                _place(mono, int(tm * sr), v, g * 0.8)
            if kick_t and sp["rumble_amount"] > 0:
                ks = kick_t["synth"]
                kv = kick_voice(sr, ks["pitch"], ks["depth"], ks["pitch_decay"], ks["amp_decay"], 0.0, 1.0)
                train = np.zeros(n, dtype=np.float32)
                for tm in kick_times:
                    if tid in bar_map[min(int(tm / (sd * 16)), total - 1)]:
                        _place(train, int(tm * sr), kv, 1.0)
                ir = reverb_ir(sr, round(m["rumble_decay"], 2), 5)[0]
                rum = signal.fftconvolve(train, ir)[:n]
                fc = np.full(n, m["sub_cutoff"])
                if "rumble.cutoff" in lanes:
                    fc = lane_values(lanes["rumble.cutoff"], bar_axis)
                rum = tv_filter(rum, sr, fc)
                rum = signal.sosfilt(_sos("lowpass", m["sub_cutoff"] * 1.2, sr), rum)
                rum = np.tanh(rum * sp["saturation"] * 1.5)
                rum = signal.sosfilt(_sos("highpass", 30, sr), rum)
                mono += (rum * sp["rumble_amount"] * 0.7).astype(np.float32)
        elif role == "perc":
            drive = m["drive"] * (1 + p["distortion"])
            for tm, st, g in ev:
                f = sp["freq"] * 2 ** ((st.get("pitch", 60) - 60) / 12.0)
                v = metal_voice(sr, round(f, 1), sp["ratio"], sp["index"], sp["decay"], round(drive, 2))
                _place(mono, int(tm * sr), v, g * 0.6)
        elif role == "hats":
            for tm, st, g in ev:
                dec = (sp["open_decay"] if st.get("pitch") == 46 else sp["closed_decay"]) * m["hat_decay"]
                _place(mono, int(tm * sr), hat_voice(sr, round(dec, 3), sp["tone"]), g)
        elif role == "stabs":
            for tm, st, g in ev:
                notes = tuple(int(st.get("pitch", 60)) + iv for iv in st.get("chord", [0, 3, 7]))
                v = stab_voice(sr, notes, round(st.get("gate", 1) * sd, 4), sp["cutoff"], sp["env_amt"], sp["detune"])
                _place(mono, int(tm * sr), v, g * 0.7)
            if "stabs.cutoff" in lanes:
                mono = tv_filter(mono, sr, lane_values(lanes["stabs.cutoff"], bar_axis)).astype(np.float32)
            # ping-pong delay
            stereo = np.stack([mono, mono]) * 0.85
            dl = int(sp["delay_steps"] * sd * sr)
            gain, k = m["echo_mix"], 1
            while gain > 0.01 and dl * k < n and m["echo_mix"] > 0:
                ch = k % 2
                stereo[ch, dl * k:] += mono[: n - dl * k] * gain * (0.5 + 0.5 * p["width"])
                stereo[1 - ch, dl * k:] += mono[: n - dl * k] * gain * (0.5 - 0.5 * p["width"])
                gain *= max(m["delay_fb"], 0.05)
                k += 1
        # sidechain ducking (trigger tap = kick pattern, pre-fader)
        for sc in project.get("sidechains", []):
            if not sc.get("enabled", True):
                continue
            for tg in sc["targets"]:
                if tg["track"] == tid and kick_times:
                    imp = np.zeros(n, dtype=np.float32)
                    for tm in kick_times:
                        i = int(tm * sr)
                        if i < n:
                            imp[i] = 1.0
                    rel = tg.get("release_ms", 140) / 1000.0
                    kern = np.exp(-np.arange(int(sr * rel * 5)) / (sr * rel)).astype(np.float32)
                    env = np.clip(signal.fftconvolve(imp, kern)[:n], 0, 1)
                    duck = (1 - tg.get("depth", 0.5) * env).astype(np.float32)
                    mono *= duck
                    if stereo is not None:
                        stereo *= duck
        vol = 10 ** (t.get("volume", 0.0) / 20.0)
        pan = (t.get("pan", 0.0) + 1) * np.pi / 4
        if stereo is None:
            stereo = np.stack([mono * np.cos(pan), mono * np.sin(pan)]) * np.sqrt(2)
        stereo *= vol
        master += stereo
        rev_bus += stereo * t.get("send_a", 0.0) * m["reverb_send"] * 2

    if np.any(rev_bus):
        ir = reverb_ir(sr, round(1.6 + 1.6 * p["hypnotic"], 2))
        master += np.stack([signal.fftconvolve(rev_bus[c], ir[c])[:n] for c in range(2)]) * 0.5

    if loop_wrap and mode != "arrangement":
        master[:, :tail] += master[:, length:length + tail]
        master = master[:, :length]
    bar_axis = bar_axis[: master.shape[1]]

    # master chain: filter -> drive -> crush -> volume auto -> limiter
    fc = np.full(master.shape[1], xy["cutoff"])
    if "master.cutoff" in lanes:
        fc = np.minimum(fc, lane_values(lanes["master.cutoff"], bar_axis))
    if fc.min() < 19000:
        master = np.stack([tv_filter(master[c], sr, fc) for c in range(2)])
    if xy["drive"] > 1.01:
        master = np.tanh(master * xy["drive"]) / np.tanh(xy["drive"])
    if m["crush_bits"] is not None:
        q = 2 ** (m["crush_bits"] - 1)
        master = np.round(master * q) / q
    if "master.volume" in lanes:
        master *= 10 ** (lane_values(lanes["master.volume"], bar_axis) / 20.0)
    master = np.nan_to_num(master)
    master, gr = limiter(master, sr)
    if repeat:
        master = beat_repeat(master, sr, sd, int(repeat))
    return master.astype(np.float32), {"bars": total, "seconds": master.shape[1] / sr, "max_gain_reduction_db": gr}


def beat_repeat(x, sr, sd, division):
    """Buffer retrigger: 2nd half of each bar repeats a 1/division slice captured at the half-bar."""
    bar = int(16 * sd * sr)
    sl = max(64, int(sd * 16 / division * sr))
    fade = np.minimum(1, np.minimum(np.arange(sl), np.arange(sl)[::-1]) / (0.002 * sr))
    out = x.copy()
    for b in range(0, x.shape[1] - bar + 1, bar):
        h = b + bar // 2
        piece = x[:, h:h + sl] * fade
        reps = int(np.ceil((b + bar - h) / sl))
        out[:, h:b + bar] = np.tile(piece, reps)[:, : b + bar - h]
    return out


def limiter(x, sr, ceiling=0.94, release=0.08, blk=64):
    n = x.shape[1]
    nb = int(np.ceil(n / blk))
    pk = np.pad(np.max(np.abs(x), axis=0), (0, nb * blk - n)).reshape(nb, blk).max(1)
    need = np.maximum(1.0, pk / ceiling)
    need = np.maximum(need, np.concatenate([need[1:], need[-1:]]))  # 1-block lookahead
    rc = math.exp(-blk / (release * sr))
    g = np.empty(nb)
    cur = 1.0
    for i in range(nb):
        tgt = 1.0 / need[i]
        cur = tgt if tgt < cur else tgt + (cur - tgt) * rc
        g[i] = cur
    gain = np.interp(np.arange(n), np.arange(nb) * blk, g)
    y = np.clip(x * gain, -ceiling, ceiling)
    return y, round(float(-20 * np.log10(g.min())), 2)


# ---------------------------------------------------------------- metering
def _biquad_rbj(kind, fc, q, gain_db, sr):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    if kind == "highshelf":
        b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * alpha), -2 * A * ((A - 1) + (A + 1) * c),
             A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * alpha, 2 * ((A - 1) - (A + 1) * c),
             (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * alpha]
    else:  # highpass
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
        a = [1 + alpha, -2 * c, 1 - alpha]
    return np.array(b) / a[0], np.array(a) / a[0]


def measure(x, sr):
    """Peak dBFS, RMS dBFS, integrated loudness (ITU-R BS.1770-4 K-weighted, gated)."""
    peak = float(np.max(np.abs(x))) + 1e-12
    rms = float(np.sqrt(np.mean(x ** 2))) + 1e-12
    b1, a1 = _biquad_rbj("highshelf", 1681.97, 0.7072, 4.0, sr)
    b2, a2 = _biquad_rbj("highpass", 38.135, 0.5003, 0.0, sr)
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=1), axis=1)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    zs = [np.sum(np.mean(y[:, i:i + blk] ** 2, axis=1)) for i in range(0, y.shape[1] - blk + 1, hop)]
    lufs = None
    if zs:
        zs = np.array(zs)
        L = -0.691 + 10 * np.log10(zs + 1e-12)
        g = zs[L > -70]
        if len(g):
            rel = -0.691 + 10 * np.log10(np.mean(g)) - 10
            g2 = zs[(L > -70) & (L > rel)]
            if len(g2):
                lufs = round(float(-0.691 + 10 * np.log10(np.mean(g2))), 2)
    corr = float(np.corrcoef(x[0], x[1])[0, 1]) if np.std(x[0]) > 0 and np.std(x[1]) > 0 else 1.0
    return {"peak_dbfs": round(20 * math.log10(peak), 2), "rms_dbfs": round(20 * math.log10(rms), 2),
            "lufs_integrated": lufs, "stereo_correlation": round(corr, 3),
            "clipped_samples": int(np.sum(np.abs(x) >= 0.999))}


# ---------------------------------------------------------------- WAV
def encode_wav(x, sr, bits=16, dither=True, normalize=False):
    x = np.nan_to_num(x.astype(np.float64))
    if normalize:
        pk = np.max(np.abs(x))
        if pk > 0:
            x = x * (10 ** (-1 / 20) / pk)
    inter = x.T.reshape(-1)
    ch = x.shape[0]
    if bits == 32:
        data = inter.astype("<f4").tobytes()
        fmt = 3
    elif bits in (16, 24):
        full = 2 ** (bits - 1)
        s = inter * (full - 1)
        if dither:
            r = np.random.default_rng(1)
            s = s + (r.random(len(s)) - r.random(len(s)))
        q = np.clip(np.round(s), -full, full - 1).astype(np.int32)
        if bits == 16:
            data = q.astype("<i2").tobytes()
        else:
            data = q.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        fmt = 1
    else:
        raise ValueError("bits must be 16, 24 or 32")
    ba = ch * bits // 8
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, fmt, ch, sr, sr * ba, ba, bits)
    hdr += b"data" + struct.pack("<I", len(data))
    return hdr + data


def parse_wav_header(b):
    fmt, ch, sr, _, ba, bits = struct.unpack("<HHIIHH", b[20:36])
    size = struct.unpack("<I", b[40:44])[0]
    return {"format": fmt, "channels": ch, "sr": sr, "bits": bits, "frames": size // ba}
