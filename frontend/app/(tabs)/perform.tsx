import React, { useEffect, useRef, useState } from "react";
import { PanResponder, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { createAudioPlayer, AudioPlayer } from "expo-audio";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useEngine } from "@/src/engine";
import { Transport } from "@/src/components/Transport";
import { Btn, Chip, Label, Mono, Panel, ParamSlider } from "@/src/ui";
import { API } from "@/src/api";
import { usesNativeTabs } from "@/src/navigation";
import { colors, fontSize, radius, spacing } from "@/src/theme";

const VOICES = ["kick", "rumble", "perc_lo", "perc_hi", "hat_closed", "hat_open", "stab_i", "stab_iv", "stab_vi", "stab_v",
  "sub_root", "sub_fifth", "riser", "impact", "noise_hit", "rim"];

function XYPad({ x, y, onCommit, display }: { x: number; y: number; onCommit: (x: number, y: number) => void; display: string }) {
  const [size, setSize] = useState({ w: 1, h: 1 });
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const start = useRef({ x: 0, y: 0 });
  const last = useRef({ x, y });
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const commit = useRef(onCommit);
  commit.current = onCommit;
  const calc = (px: number, py: number) => ({
    x: Math.max(0, Math.min(1, px / sizeRef.current.w)), y: Math.max(0, Math.min(1, 1 - py / sizeRef.current.h)),
  });
  const pr = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true, onMoveShouldSetPanResponder: () => true, onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: (e) => { start.current = { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY }; last.current = calc(start.current.x, start.current.y); setPos(last.current); },
    onPanResponderMove: (_, g) => { last.current = calc(start.current.x + g.dx, start.current.y + g.dy); setPos(last.current); },
    onPanResponderRelease: () => { commit.current(+last.current.x.toFixed(3), +last.current.y.toFixed(3)); setPos(null); },
  })).current;
  const raw = pos ?? { x, y };
  const c = { x: Math.max(0.04, Math.min(0.96, raw.x)), y: Math.max(0.06, Math.min(0.94, raw.y)) };
  return (
    <View testID="xy-pad" onLayout={(e) => setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} style={st.xy} {...pr.panHandlers}>
      <View pointerEvents="none" style={[st.xyH, { top: `${(1 - c.y) * 100}%` }]} />
      <View pointerEvents="none" style={[st.xyV, { left: `${c.x * 100}%` }]} />
      <View pointerEvents="none" style={[st.dot, { left: `${c.x * 100}%`, top: `${(1 - c.y) * 100}%` }]} />
      <Mono style={st.xyLabel}>X CUTOFF · Y DRIVE</Mono>
      <Mono testID="xy-display" style={st.xyValue}>{display}</Mono>
    </View>
  );
}

export default function Perform() {
  const e = useEngine();
  const p = e.project;
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [mode, setMode] = useState<"drum" | "clip">("drum");
  const [lit, setLit] = useState<number | null>(null);
  const players = useRef<Record<string, AudioPlayer>>({});

  useEffect(() => {
    Object.values(players.current).forEach((pl) => pl.remove());
    players.current = {};
    if (!p) return;
    VOICES.forEach((v) => { players.current[v] = createAudioPlayer({ uri: `${API}/projects/${p.id}/oneshot/${v}.wav?rev=${p.revision}` }); });
    return () => { Object.values(players.current).forEach((pl) => pl.remove()); players.current = {}; };
  }, [p?.id, p?.revision]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!p) {
    return (
      <View style={st.root}>
        <Transport />
        <View testID="perform-empty" style={{ padding: spacing.xl, gap: spacing.lg }}>
          <Mono>No performance template active.</Mono>
          <Btn testID="perform-new-project" kind="primary" label="NEW PROJECT" icon="plus" onPress={() => router.push("/new")} />
        </View>
      </View>
    );
  }
  const mask = e.perf.mask ?? p.tracks.map((t) => t.id);
  const hit = (i: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setLit(i);
    setTimeout(() => setLit((l) => (l === i ? null : l)), 120);
    if (mode === "drum") {
      const pl = players.current[VOICES[i]];
      if (pl) { pl.seekTo(0).catch(() => {}); pl.play(); }
    } else {
      const t = p.tracks[i];
      if (!t) return;
      const next = mask.includes(t.id) ? mask.filter((x) => x !== t.id) : [...mask, t.id];
      e.setPerf({ mask: next });
      if (!e.playing) e.play();
    }
  };
  const toggleRec = () => {
    if (!e.recording) { e.setRecording(true); e.notify("Recording scene launches - launch scenes now"); return; }
    e.setRecording(false);
    const L = e.launches;
    if (!L.length) { e.notify("Nothing recorded (launch at least one scene)", "err"); return; }
    const barMs = (60 / p.bpm) * 4 * 1000;
    const launches = L.map((l, i) => ({ section: l.section, bars: i < L.length - 1 ? Math.max(1, Math.round((L[i + 1].at - l.at) / barMs)) : p.sections[l.section].bars }));
    e.applyOps([{ type: "RecordPerformance", launches }], "Record session into arrangement").then((x) => {
      if (!x) return;
      e.setPerf({ section: null, mask: null });
      e.notify(`Captured ${launches.length} launches into arrangement`);
    });
  };

  return (
    <View style={st.root}>
      <Transport />
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: bottomChrome + spacing.xl }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          <Chip testID="pad-mode-drum" label="DRUM" selected={mode === "drum"} onPress={() => setMode("drum")} />
          <Chip testID="pad-mode-clip" label="CLIP" selected={mode === "clip"} onPress={() => setMode("clip")} />
          <Chip testID="perf-rec-toggle" label={e.recording ? "● REC ON" : "○ REC"} selected={e.recording} onPress={toggleRec} />
          {[null, 4, 8, 16, 32].map((r) => (
            <Chip key={String(r)} testID={`beat-repeat-${r ?? "off"}`} label={r ? `RPT 1/${r}` : "RPT OFF"} selected={e.perf.repeat === r}
              onPress={() => { e.setPerf({ repeat: r }); if (r && !e.playing) e.play(); }} />
          ))}
        </ScrollView>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <View style={st.pads}>
            {VOICES.map((v, i) => {
              const t = p.tracks[i];
              const on = mode === "clip" && t && mask.includes(t.id);
              return (
                <Pressable key={v} testID={`pad-${i}`} onPressIn={() => hit(i)} disabled={mode === "clip" && !t}
                  style={[st.pad, { borderColor: lit === i ? colors.brandPrimary : colors.border,
                    backgroundColor: lit === i ? colors.surfaceInverse : on ? (t?.color ?? colors.surfaceTertiary) : colors.surfaceTertiary,
                    opacity: mode === "clip" && !t ? 0.3 : 1 }]}>
                  <Text numberOfLines={2} style={[st.padT, on && { color: colors.onBrandPrimary }]}>
                    {mode === "drum" ? v.replace("_", " ").toUpperCase() : t ? t.name : "—"}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          <View style={st.scenes}>
            <Label>SCENES</Label>
            {p.sections.map((s, i) => (
              <Pressable key={i} testID={`scene-launch-${i}`} onPress={() => { e.setPerf({ section: i, mask: null }); if (!e.playing) e.play(); }}
                style={[st.scene, e.perf.section === i && !e.override && { borderColor: colors.brandPrimary, backgroundColor: colors.surfaceInverse }]}>
                <Text numberOfLines={1} style={st.sceneT}>▶ {s.name}</Text>
              </Pressable>
            ))}
            <Pressable testID="return-to-arrangement" onPress={() => { e.setPerf({ section: null, mask: null, repeat: null }); e.playUrl(`${API}/projects/${p.id}/render.wav?mode=arrangement&rev=${p.revision}`); }} style={st.scene}>
              <Text numberOfLines={1} style={[st.sceneT, { color: colors.brandSecondary }]}>↩ ARRANGE</Text>
            </Pressable>
            <Pressable testID="stop-all-clips" onPress={e.stop} style={st.scene}><Text style={[st.sceneT, { color: colors.error }]}>■ STOP</Text></Pressable>
          </View>
        </View>
        <Mono style={{ color: colors.muted, fontSize: fontSize.sm }}>
          Loops are rendered by the server engine; launches, repeat and macro moves take effect on the next render (~0.2–1 s).
        </Mono>
        <Panel title="XY MORPH">
          <XYPad x={p.xy.x} y={p.xy.y} display={`${p.xy_display.cutoff} · ${p.xy_display.drive}`} onCommit={(x, y) => e.applyOps([{ type: "SetXY", x, y }])} />
          <Btn small testID="xy-reset" label="RESET XY" onPress={() => e.applyOps([{ type: "SetXY", x: 1, y: 0 }])} />
        </Panel>
        <Panel title="MACROS">
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {(e.meta?.snapshots ?? []).map((n: string) => (
              <Chip key={n} testID={`snapshot-${n.replace(/\W+/g, "-").toLowerCase()}`} label={n}
                onPress={() => e.applyOps([{ type: "ApplyMacroSnapshot", name: n, amount: 1 }]).then((x) => x && e.notify(`Snapshot: ${n}`))} />
            ))}
          </ScrollView>
          <View style={st.macros}>
            {p.macros.map((m, i) => (
              <View key={i} style={{ width: "48%" }}>
                <ParamSlider testID={`macro-${i + 1}`} label={`${i + 1} ${e.meta?.macro_names?.[i] ?? ""}`} value={m} min={0} max={1}
                  format={(v) => (Math.abs(v - m) < 1e-6 ? p.macro_display[i] : `${Math.round(v * 100)}%`)}
                  onCommit={(v) => e.applyOps([{ type: "SetMacro", index: i, value: +v.toFixed(3) }])} />
              </View>
            ))}
          </View>
        </Panel>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  pads: { flex: 1, flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  pad: { width: "22.5%", aspectRatio: 1, borderWidth: 1, borderRadius: radius.md, padding: spacing.sm, justifyContent: "flex-end" },
  padT: { color: colors.onSurface, fontSize: 9, fontWeight: "700" },
  scenes: { width: 96, gap: spacing.sm },
  scene: { minHeight: 36, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, justifyContent: "center", paddingHorizontal: spacing.sm, backgroundColor: colors.surfaceSecondary },
  sceneT: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "600" },
  xy: { height: 180, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, overflow: "hidden" },
  xyH: { position: "absolute", left: 0, right: 0, height: 1, backgroundColor: colors.brandSecondary, opacity: 0.5 },
  xyV: { position: "absolute", top: 0, bottom: 0, width: 1, backgroundColor: colors.brandSecondary, opacity: 0.5 },
  dot: { position: "absolute", width: 20, height: 20, marginLeft: -10, marginTop: -10, borderRadius: 10, backgroundColor: colors.brandPrimary },
  xyLabel: { position: "absolute", left: 6, top: 4, fontSize: fontSize.sm, color: colors.muted },
  xyValue: { position: "absolute", left: 6, bottom: 4, fontSize: fontSize.sm, color: colors.brandSecondary },
  macros: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: spacing.md },
});
