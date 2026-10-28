import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { storage } from "@/src/utils/storage";
import { API, api, ApiError } from "@/src/api";

export type Step = { on: boolean; vel: number; prob: number; ratchet: number; micro: number; gate: number; pitch?: number; chord?: number[] };
export type Track = {
  id: string; role: string; name: string; group: string; color: string; mute: boolean; solo: boolean; volume: number; pan: number;
  send_a: number; synth: Record<string, number>; preset?: string; layer_seed: number; pattern: Step[]; provenance: any;
};
export type Project = {
  id: string; name: string; template: string; seed: number; bpm: number; key: string; scale: string; time_sig: number[];
  params: Record<string, number>; macros: number[]; macro_display: string[]; xy: { x: number; y: number };
  xy_display: { cutoff: string; drive: string }; tracks: Track[]; sections: { name: string; bars: number; active: string[] }[];
  automation: any[]; sidechains: any[]; revision: number; length_bars: number;
};
type Perf = { section: number | null; mask: string[] | null; repeat: number | null };
type Toast = { msg: string; kind: "ok" | "err" } | null;

type Ctx = {
  project: Project | null; meta: any; busy: boolean; toast: Toast; playing: boolean; rendering: boolean; position: number;
  perf: Perf; override: string | null;
  setPerf: (p: Partial<Perf>) => void; notify: (msg: string, kind?: "ok" | "err") => void;
  openProject: (id: string) => Promise<void>; setProject: (p: Project | null) => void;
  applyOps: (ops: any[], label?: string) => Promise<Project | null>; undo: () => Promise<void>; redo: () => Promise<void>;
  play: () => void; stop: () => void; playUrl: (url: string) => void; recording: boolean; setRecording: (r: boolean) => void;
  launches: { section: number; at: number }[];
};

const EngineCtx = createContext<Ctx>(null as any);
export const useEngine = () => useContext(EngineCtx);

export function EngineProvider({ children }: { children: React.ReactNode }) {
  const [project, setProject] = useState<Project | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [playing, setPlaying] = useState(false);
  const [perf, setPerfState] = useState<Perf>({ section: null, mask: null, repeat: null });
  const [override, setOverride] = useState<string | null>(null);
  const [recording, setRecordingState] = useState(false);
  const launches = useRef<{ section: number; at: number }[]>([]);
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const toastTimer = useRef<any>(null);

  const notify = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    setToast({ msg, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3200);
  }, []);

  useEffect(() => {
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => {});
    api("/meta").then(setMeta).catch((e) => notify(`Engine offline: ${e.message}`, "err"));
    storage.getItem("current_project", null as string | null).then((id) => {
      if (id) api<Project>(`/projects/${id}`).then(setProject).catch(() => storage.removeItem("current_project"));
    });
  }, [notify]);

  const openProject = useCallback(async (id: string) => {
    const p = await api<Project>(`/projects/${id}`);
    setProject(p);
    setPerfState({ section: null, mask: null, repeat: null });
    await storage.setItem("current_project", id);
  }, []);

  const applyOps = useCallback(async (ops: any[], label?: string) => {
    if (!project) return null;
    setBusy(true);
    try {
      const r = await api<{ project: Project; applied: string[] }>(`/projects/${project.id}/ops`, {
        body: { base_revision: project.revision, ops, label },
      });
      setProject(r.project);
      return r.project;
    } catch (e: any) {
      notify(e instanceof ApiError && e.status === 409 ? "Project changed elsewhere - reloaded" : e.message, "err");
      if (e instanceof ApiError && e.status === 409) setProject(await api(`/projects/${project.id}`));
      return null;
    } finally {
      setBusy(false);
    }
  }, [project, notify]);

  const history = useCallback(async (kind: "undo" | "redo") => {
    if (!project) return;
    try {
      const r = await api<any>(`/projects/${project.id}/${kind}`, { method: "POST" });
      setProject(r.project);
      notify(`${kind === "undo" ? "Undid" : "Redid"}: ${r.undone ?? r.redone}`);
    } catch (e: any) {
      notify(e.message, "err");
    }
  }, [project, notify]);

  const loopUrl = useMemo(() => {
    if (!project) return null;
    const q = [`rev=${project.revision}`, "bars=4"];
    if (perf.section !== null) q.push("mode=section", `section=${perf.section}`);
    else q.push("mode=loop");
    if (perf.mask) q.push(`mask=${perf.mask.join(",")}`);
    if (perf.repeat) q.push(`repeat=${perf.repeat}`);
    return `${API}/projects/${project.id}/render.wav?${q.join("&")}`;
  }, [project, perf]);

  const currentUrl = override ?? loopUrl;
  useEffect(() => {
    if (!playing || !currentUrl) return;
    player.replace({ uri: currentUrl });
    player.loop = true;
    player.play();
  }, [currentUrl, playing, player]);

  const stop = useCallback(() => {
    player.pause();
    player.seekTo(0).catch(() => {});
    setPlaying(false);
    setOverride(null);
  }, [player]);

  const setPerf = useCallback((p: Partial<Perf>) => {
    setOverride(null);
    if (p.section !== undefined && p.section !== null && recording) launches.current.push({ section: p.section, at: Date.now() });
    setPerfState((s) => ({ ...s, ...p }));
  }, [recording]);

  const setRecording = useCallback((r: boolean) => {
    if (r) launches.current = [];
    setRecordingState(r);
  }, []);

  const value: Ctx = {
    project, meta, busy, toast, playing, perf, override, notify, openProject, applyOps, setPerf,
    rendering: playing && (!status.isLoaded || status.isBuffering),
    position: status.currentTime ?? 0,
    setProject: (p) => {
      setProject(p);
      if (p) storage.setItem("current_project", p.id);
    },
    undo: () => history("undo"), redo: () => history("redo"),
    play: () => setPlaying(true), stop,
    playUrl: (url) => { setOverride(url); setPlaying(true); },
    recording, setRecording, launches: launches.current,
  };
  return <EngineCtx.Provider value={value}>{children}</EngineCtx.Provider>;
}
