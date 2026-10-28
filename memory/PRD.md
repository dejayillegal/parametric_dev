# PARAMETRIC ALS — AI Techno DAW Engine (mobile, Expo)

## Original problem statement
Very large spec ("MASTER IMPLEMENTATION PROMPT — PARAMETRIC ALS v1.0"): Ableton-class AI techno DAW with lossless .als import/inspection/safe export, real audio engine, arrangement/session/performance, four techno generator layers, procedural templates, humanization, 8-macro rack, automation, AI completion plans with manual Ableton steps, sidechain studio, WAV/MIDI export, invariants INV-001..017, no fake functionality.

## User choices
- First version: techno generator + playback + ALS import/inspection + live performance
- Audio: server-rendered loops played on the phone (real-time on-device synthesis needs native build — not done)
- AI: rule-based typed plans + optional Claude (claude-sonnet-5-5 via Emergent LLM key) explanations, consent toggle

## Architecture
- Backend FastAPI + MongoDB. `engine/`: `dsp.py` (numpy/scipy synthesis: 909 kick, rumble sub w/ kick-derived reverb rumble, FM metallic perc, 909 hats, detuned saw stabs, ping-pong delay, reverb, sidechain ducking, time-varying filters, automation lanes, master filter/drive/crush/limiter, beat repeat, BS.1770 LUFS, 16/24/32f WAV), `composer.py` (deterministic seeded generators, 3 templates, 5 rumble presets, humanization), `ops.py` (22 typed validated operations), `planner.py` (features → missingness → plans with ops + manual steps), `als.py` (safe gzip/XML parse, Live 10/11/12 adapters, track tree, clips/notes, devices, sidechain routing resolution, automation target resolution, assets, invariants, line-level patch compiler for SetTempo/RenameTrack with re-import verification), `fixture.py` (original synthetic Live-11-style test set).
- Undo/redo: pre-op snapshots in `history`/`redo` collections; revision preconditions (409 on stale).
- Frontend Expo Router: tabs Studio / Perform / Projects / AI; stacks /new, /track/[id], /arrange, /als/[id]. expo-audio plays rendered loop URLs; pads use one-shot WAVs.

## Implemented (2026-06)
- Project create (templates/empty, seed, BPM, key, scale, 7 character params, length), list/open/duplicate/delete
- Studio step grids, mute/solo, add layers; track editor (step inspector, velocity lane, pattern length/poly, rotate, regenerate, presets, humanize, synth params, mixer, sidechain)
- Perform: 4x4 pads (drum/clip modes), scenes, return to arrangement, beat repeat, scene recording into arrangement, XY morph, 8 macros w/ units, snapshots
- Arrange: section timeline toggles, generate sections, automation lane presets, WAV render (arrangement/loop/stems, 16/24/32f, 44.1/48k, normalize), measurement, MIDI export
- AI: 8 modes, analysis, plan cards (preview, A/B, locate, params, manual, explain, reject, apply)
- ALS: import + synthetic fixture, overview/tree/sidechains/diagnostics/export (no-op byte-identical, typed patch with diff + invariants), honest "native reopen NOT verified"
- Tests: backend/tests/test_engine.py + test_api_daw.py (66 pass)

## Known limitations
- Native Ableton reopen verification not possible here; native device insertion = manual instructions only
- Real-time on-device synthesis / mic recording / Web MIDI not implemented (render latency ~0.2–1s)
- No piano roll beyond step/pitch editing; no audio clip import into Parametric projects

## Backlog
- P0: piano-roll note editor; audio sample import (object storage)
- P1: more native-safe ALS ops (clip move, mixer values), MIDI import, continuous loop crossfade on edits
- P2: real-time native audio engine (dev build), MIDI controller mapping, cloud workspaces
