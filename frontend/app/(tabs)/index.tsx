import React from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { Transport } from "@/src/components/Transport";
import { StepGrid } from "@/src/components/StepGrid";
import { Btn, Chip, Icon, Label, Mono } from "@/src/ui";
import { usesNativeTabs } from "@/src/navigation";
import { colors, fontSize, radius, spacing } from "@/src/theme";

export default function Studio() {
  const e = useEngine();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const p = e.project;
  const sd = p ? 60 / p.bpm / 4 : 1;
  const g = Math.floor(e.position / sd);

  if (!p) {
    return (
      <View style={st.root}>
        <Transport />
        <View testID="studio-empty" style={st.empty}>
          <Mono style={{ fontSize: fontSize.xl }}>NO PROJECT LOADED</Mono>
          <Text style={st.muted}>Generate a techno project from a template, or import an Ableton Live Set to inspect.</Text>
          <Btn testID="studio-new-project" kind="primary" icon="plus" label="NEW PROJECT" onPress={() => router.push("/new")} />
          <Btn testID="studio-open-projects" icon="folder-music" label="OPEN / IMPORT .ALS" onPress={() => router.navigate("/projects")} />
        </View>
      </View>
    );
  }
  const scTargets = new Set(p.sidechains.flatMap((s: any) => s.targets.map((t: any) => t.track)));
  return (
    <View style={st.root}>
      <Transport />
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.sm, paddingBottom: bottomChrome + spacing.xl }}>
        <View style={st.headRow}>
          <Label>TRACKS · {p.tracks.length}</Label>
          <Label>{p.params && `DENS ${p.params.density.toFixed(2)} · TENS ${p.params.tension.toFixed(2)} · GROOVE ${p.params.groove.toFixed(2)}`}</Label>
        </View>
        {p.tracks.map((t) => {
          const L = t.pattern.length;
          return (
            <View key={t.id} testID={`track-row-${t.id}`} style={st.track}>
              <View style={[st.colorBar, { backgroundColor: t.color }]} />
              <View style={{ flex: 1, gap: spacing.sm }}>
                <View style={st.trackHead}>
                  <Pressable testID={`track-open-${t.id}`} onPress={() => router.push(`/track/${t.id}`)} style={{ flex: 1, minHeight: 36, justifyContent: "center" }}>
                    <Mono numberOfLines={1} style={{ fontWeight: "700" }}>{t.name} <Text style={st.muted}>› {t.group}</Text></Mono>
                    <Mono style={st.meta}>{L} st{L !== 16 ? " · POLY" : ""} · {t.volume.toFixed(1)} dB{scTargets.has(t.id) ? " · SC←KICK" : ""}</Mono>
                  </Pressable>
                  <Pressable testID={`track-mute-${t.id}`} accessibilityLabel="Mute" onPress={() => e.applyOps([{ type: "SetTrackParam", track: t.id, key: "mute", value: !t.mute }])}
                    style={[st.ms, t.mute && { backgroundColor: colors.brandPrimary }]}><Text style={[st.msT, t.mute && { color: colors.onBrandPrimary }]}>M</Text></Pressable>
                  <Pressable testID={`track-solo-${t.id}`} accessibilityLabel="Solo" onPress={() => e.applyOps([{ type: "SetTrackParam", track: t.id, key: "solo", value: !t.solo }])}
                    style={[st.ms, t.solo && { backgroundColor: colors.brandSecondary }]}><Text style={[st.msT, t.solo && { color: colors.onBrandSecondary }]}>S</Text></Pressable>
                  <Pressable testID={`track-edit-${t.id}`} accessibilityLabel="Edit track" onPress={() => router.push(`/track/${t.id}`)} style={st.ms}>
                    <Icon name="tune-variant" size={16} color={colors.onSurface} />
                  </Pressable>
                </View>
                <StepGrid testID={`grid-${t.id}`} pattern={t.pattern} color={t.color} playStep={e.playing ? g % L : null}
                  onPress={(i) => e.applyOps([{ type: "ToggleStep", track: t.id, index: i }])} />
              </View>
            </View>
          );
        })}
        <Label style={{ marginTop: spacing.md }}>ADD GENERATOR LAYER</Label>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {["kick", "rumble", "perc", "hats", "stabs"].map((r) => (
            <Chip key={r} testID={`add-layer-${r}`} label={`+ ${e.meta?.roles?.[r]?.name ?? r}`}
              onPress={() => e.applyOps([{ type: "AddLayer", role: r, seed: p.seed + p.tracks.length }]).then((x) => x && e.notify(`Added ${r} layer`))} />
          ))}
        </ScrollView>
        <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
          <Btn testID="studio-arrange-button" icon="timeline-outline" label="ARRANGE · AUTOMATION · EXPORT" kind="cyan" style={{ flex: 1 }} onPress={() => router.push("/arrange")} />
        </View>
        <Btn testID="studio-new-project-2" icon="plus" label="NEW PROJECT" onPress={() => router.push("/new")} />
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  empty: { flex: 1, padding: spacing.xl, gap: spacing.lg, justifyContent: "center" },
  muted: { color: colors.muted, fontSize: fontSize.base },
  headRow: { flexDirection: "row", justifyContent: "space-between" },
  track: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, overflow: "hidden" },
  colorBar: { width: 4 },
  trackHead: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingTop: spacing.sm, paddingRight: spacing.sm, paddingLeft: spacing.md },
  meta: { color: colors.muted, fontSize: fontSize.sm },
  ms: { width: 36, height: 36, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  msT: { color: colors.onSurface, fontWeight: "700", fontSize: fontSize.base },
});
