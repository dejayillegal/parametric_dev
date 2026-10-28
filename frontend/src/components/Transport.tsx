import React, { useRef } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useEngine } from "@/src/engine";
import { Icon, Mono } from "@/src/ui";
import { colors, fontSize, mono, radius, spacing } from "@/src/theme";

export function Transport() {
  const e = useEngine();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const taps = useRef<number[]>([]);
  const p = e.project;
  const sd = p ? 60 / p.bpm / 4 : 1;
  const g = Math.floor(e.position / sd);
  const pos = p ? `${Math.floor(g / 16) + 1}.${Math.floor((g % 16) / 4) + 1}.${(g % 4) + 1}` : "-.-.-";

  const tap = () => {
    const now = Date.now();
    taps.current = [...taps.current.filter((t) => now - t < 3000), now].slice(-6);
    if (taps.current.length >= 3 && p) {
      const iv = (taps.current[taps.current.length - 1] - taps.current[0]) / (taps.current.length - 1);
      const bpm = Math.max(60, Math.min(200, Math.round(60000 / iv)));
      e.applyOps([{ type: "SetTempo", bpm }], `Tap tempo ${bpm}`);
    }
  };
  const nudge = (d: number) => p && e.applyOps([{ type: "SetTempo", bpm: Math.max(60, Math.min(200, p.bpm + d)) }]);

  return (
    <View testID="transport-bar" style={[st.bar, { paddingTop: insets.top + spacing.sm }]}>
      <View style={st.row}>
        <Pressable testID="transport-play-button" accessibilityLabel={e.playing ? "Stop" : "Play"} disabled={!p}
          onPress={e.playing ? e.stop : e.play} style={[st.play, { backgroundColor: e.playing ? colors.brandPrimary : colors.surfaceTertiary }]}>
          {e.rendering ? <ActivityIndicator testID="transport-rendering" size="small" color={colors.onBrandPrimary} /> :
            <Icon name={e.playing ? "stop" : "play"} size={22} color={e.playing ? colors.onBrandPrimary : colors.onSurface} />}
        </Pressable>
        <View style={st.cell}>
          <Text style={st.k}>POS</Text>
          <Mono testID="transport-position" style={st.v}>{e.playing ? pos : "1.1.1"}</Mono>
        </View>
        <View style={st.bpmBox}>
          <Pressable testID="bpm-down" onPress={() => nudge(-1)} style={st.nudge}><Icon name="minus" size={14} color={colors.muted} /></Pressable>
          <Pressable testID="tap-tempo-button" onPress={tap} style={st.cell} accessibilityLabel="Tap tempo">
            <Text style={st.k}>BPM·TAP</Text>
            <Mono testID="transport-bpm" style={[st.v, { color: colors.brandPrimary }]}>{p ? p.bpm.toFixed(1) : "---"}</Mono>
          </Pressable>
          <Pressable testID="bpm-up" onPress={() => nudge(1)} style={st.nudge}><Icon name="plus" size={14} color={colors.muted} /></Pressable>
        </View>
        <View style={st.cell}>
          <Text style={st.k}>KEY</Text>
          <Mono testID="transport-key" style={st.v}>{p ? `${p.key} ${p.scale.slice(0, 4)}` : "--"}</Mono>
        </View>
        <View style={st.cell}>
          <Text style={st.k}>SEED</Text>
          <Mono testID="transport-seed" style={[st.v, { color: colors.brandSecondary }]}>{p ? p.seed : "--"}</Mono>
        </View>
        <View style={{ flexGrow: 1, flexShrink: 1 }} />
        <Pressable testID="undo-button" accessibilityLabel="Undo" disabled={!p} onPress={e.undo} style={st.icon}><Icon name="undo" size={18} color={colors.onSurface} /></Pressable>
        <Pressable testID="redo-button" accessibilityLabel="Redo" disabled={!p} onPress={e.redo} style={st.icon}><Icon name="redo" size={18} color={colors.onSurface} /></Pressable>
        <Pressable testID="open-arrange-button" accessibilityLabel="Arrange and export" disabled={!p} onPress={() => router.push("/arrange")} style={st.icon}>
          <Icon name="export-variant" size={18} color={colors.onSurface} />
        </Pressable>
      </View>
      <View style={st.sub}>
        <Mono numberOfLines={1} testID="transport-project-name" style={{ color: colors.muted, fontSize: fontSize.sm, flex: 1 }}>
          {p ? `${p.name} · r${p.revision} · ${p.time_sig.join("/")} · saved` : "no project loaded"}
        </Mono>
        <Mono testID="transport-mode" style={{ color: e.override ? colors.brandSecondary : colors.muted, fontSize: fontSize.sm }}>
          {e.override ? "PREVIEW/ARR" : e.perf.section !== null && p?.sections[e.perf.section] ? `SCENE ${p.sections[e.perf.section].name}` : "LOOP 4 BAR"}
          {e.perf.repeat ? ` · RPT 1/${e.perf.repeat}` : ""}{e.recording ? " · ●REC" : ""}
        </Mono>
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  bar: { backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, gap: spacing.xs },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  play: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  cell: { paddingHorizontal: spacing.xs, minHeight: 44, justifyContent: "center", flexShrink: 1 },
  k: { color: colors.muted, fontSize: 9, fontFamily: mono },
  v: { fontSize: fontSize.lg, fontWeight: "700" },
  bpmBox: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  nudge: { width: 26, height: 44, alignItems: "center", justifyContent: "center" },
  icon: { width: 32, height: 44, alignItems: "center", justifyContent: "center" },
  sub: { flexDirection: "row", gap: spacing.md },
});
