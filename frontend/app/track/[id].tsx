import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { StepGrid } from "@/src/components/StepGrid";
import { Btn, Chip, Icon, Label, Mono, Panel, ParamSlider } from "@/src/ui";
import { colors, fontSize, radius, spacing } from "@/src/theme";

const NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = (m: number) => `${NOTE[m % 12]}${Math.floor(m / 12) - 1}`;

function VelocityLane({ pattern, onSet, testID }: { pattern: any[]; onSet: (i: number, v: number) => void; testID: string }) {
  const H = 64;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} testID={testID}>
      {pattern.map((s, i) => (
        <Pressable key={i} testID={`${testID}-${i}`} disabled={!s.on} onPress={(e) => onSet(i, Math.max(1, Math.min(127, Math.round((1 - e.nativeEvent.locationY / H) * 127))))}
          style={{ width: 22, height: H, marginRight: i % 4 === 3 ? 6 : 2, justifyContent: "flex-end", backgroundColor: colors.surfaceTertiary, borderRadius: 2 }}>
          {s.on ? <View pointerEvents="none" style={{ height: (s.vel / 127) * H, backgroundColor: colors.brandPrimary, opacity: 0.8 }} /> : null}
        </Pressable>
      ))}
    </ScrollView>
  );
}

export default function TrackEditor() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const e = useEngine();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [sel, setSel] = useState<number | null>(null);
  const [hum, setHum] = useState({ micro: 8, ghost: 15 });
  const p = e.project;
  const t = p?.tracks.find((x) => x.id === id);
  if (!p || !t) {
    return (
      <View style={[st.root, { paddingTop: insets.top + spacing.xl, padding: spacing.xl, gap: spacing.md }]}>
        <Mono testID="track-not-found">Track not found in the current project.</Mono>
        <Btn testID="track-back" label="BACK" onPress={() => router.back()} />
      </View>
    );
  }
  const op = (o: any) => e.applyOps([{ track: t.id, ...o }]);
  const step = sel !== null ? t.pattern[sel] : null;
  const upd = (fields: any) => sel !== null && op({ type: "UpdateStep", index: sel, fields });
  const kick = p.tracks.find((x) => x.role === "kick");
  const sc = p.sidechains.flatMap((s: any) => s.targets).find((g: any) => g.track === t.id);
  const sd = 60 / p.bpm / 4;
  const playStep = e.playing ? Math.floor(e.position / sd) % t.pattern.length : null;
  const specs = e.meta?.role_params?.[t.role] ?? {};

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}>
        <Pressable testID="track-back" accessibilityLabel="Back" onPress={() => router.back()} style={st.icon}><Icon name="arrow-left" size={20} color={colors.onSurface} /></Pressable>
        <View style={[st.sw, { backgroundColor: t.color }]} />
        <View style={{ flex: 1 }}>
          <Mono testID="track-title" style={{ fontWeight: "700", fontSize: fontSize.lg }}>{t.name}</Mono>
          <Mono style={st.meta}>{e.meta?.roles?.[t.role]?.generator} · {t.group}</Mono>
        </View>
        <Pressable testID="track-play-toggle" onPress={e.playing ? e.stop : e.play} style={st.icon}>
          <Icon name={e.playing ? "stop" : "play"} size={20} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <Panel title={`PATTERN · ${t.pattern.length} STEPS`} right={
          <View style={{ flexDirection: "row", gap: spacing.xs }}>
            <Btn small testID="pattern-length-down" icon="minus" onPress={() => op({ type: "SetPatternLength", length: Math.max(1, t.pattern.length - 1) })} />
            <Btn small testID="pattern-length-up" icon="plus" onPress={() => op({ type: "SetPatternLength", length: Math.min(64, t.pattern.length + 1) })} />
            <Btn small testID="pattern-rotate" icon="rotate-right" onPress={() => op({ type: "RotatePattern", amount: 1 })} />
          </View>}>
          <StepGrid testID="editor-grid" pattern={t.pattern} color={t.color} playStep={playStep} selected={sel} size={26} onPress={(i) => setSel(i === sel ? null : i)} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
            {[16, 32, 64, 3, 5, 7, 12].map((n) => <Chip key={n} testID={`pattern-length-${n}`} label={`${n}`} selected={t.pattern.length === n} onPress={() => op({ type: "SetPatternLength", length: n })} />)}
          </ScrollView>
          <Label>VELOCITY LANE · TAP BAR HEIGHT</Label>
          <VelocityLane testID="velocity-lane" pattern={t.pattern} onSet={(i, v) => op({ type: "UpdateStep", index: i, fields: { vel: v } })} />
        </Panel>
        {step ? (
          <Panel title={`STEP ${sel! + 1}`} testID="step-inspector" right={
            <Btn small testID="step-toggle" kind={step.on ? "primary" : "default"} label={step.on ? "ON" : "OFF"} onPress={() => op({ type: "ToggleStep", index: sel })} />}>
            <ParamSlider testID="step-velocity" label="VELOCITY" value={step.vel} min={1} max={127} format={(v) => `${Math.round(v)}`} onCommit={(v) => upd({ vel: Math.round(v) })} />
            <ParamSlider testID="step-probability" label="PROBABILITY" value={step.prob} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onCommit={(v) => upd({ prob: +v.toFixed(2) })} />
            <ParamSlider testID="step-micro" label="MICROTIMING" value={step.micro} min={-25} max={25} format={(v) => `${v.toFixed(1)} ms`} onCommit={(v) => upd({ micro: +v.toFixed(1) })} accent={colors.brandSecondary} />
            <ParamSlider testID="step-gate" label="GATE" value={step.gate} min={0.1} max={4} format={(v) => `${v.toFixed(2)} st`} onCommit={(v) => upd({ gate: +v.toFixed(2) })} />
            <View style={{ flexDirection: "row", gap: spacing.xs, alignItems: "center" }}>
              <Label>RATCHET</Label>
              {[1, 2, 3, 4].map((r) => <Chip key={r} testID={`step-ratchet-${r}`} label={`${r}x`} selected={step.ratchet === r} onPress={() => upd({ ratchet: r })} />)}
            </View>
            {step.pitch !== undefined && t.role !== "kick" ? (
              <View style={{ flexDirection: "row", gap: spacing.xs, alignItems: "center" }}>
                <Label>PITCH</Label>
                <Btn small testID="step-pitch-oct-down" label="-12" onPress={() => upd({ pitch: Math.max(0, step.pitch! - 12) })} />
                <Btn small testID="step-pitch-down" icon="minus" onPress={() => upd({ pitch: Math.max(0, step.pitch! - 1) })} />
                <Mono testID="step-pitch-value" style={{ color: colors.brandPrimary, minWidth: 48, textAlign: "center" }}>{t.role === "hats" ? (step.pitch === 46 ? "OPEN" : "CLOSED") : noteName(step.pitch)}</Mono>
                <Btn small testID="step-pitch-up" icon="plus" onPress={() => upd({ pitch: Math.min(127, step.pitch! + 1) })} />
                <Btn small testID="step-pitch-oct-up" label="+12" onPress={() => upd({ pitch: Math.min(127, step.pitch! + 12) })} />
              </View>
            ) : null}
            {step.chord ? <Mono style={st.meta}>chord {step.chord.map((c) => noteName((step.pitch ?? 60) + c)).join(" ")}</Mono> : null}
          </Panel>
        ) : <Mono style={st.meta}>Tap a step above to edit velocity, probability, microtiming, gate, ratchet and pitch.</Mono>}
        <Panel title="GENERATOR">
          <Mono style={st.meta}>seed {t.layer_seed}{t.preset ? ` · preset ${t.preset}` : ""} · native target: {t.provenance?.native_target}</Mono>
          {t.role === "rumble" ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
              {Object.entries(e.meta?.rumble_presets ?? {}).map(([k, v]: any) => (
                <Chip key={k} testID={`rumble-preset-${k}`} label={v} selected={t.preset === k} onPress={() => op({ type: "RegenerateLayer", preset: k, seed: t.layer_seed })} />
              ))}
            </ScrollView>
          ) : null}
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Btn testID="regenerate-prev" icon="chevron-left" label="SEED-1" onPress={() => op({ type: "RegenerateLayer", seed: Math.max(0, t.layer_seed - 1) })} />
            <Btn testID="regenerate-next" kind="primary" icon="dice-5-outline" label="REGENERATE SEED+1" style={{ flex: 1 }} onPress={() => op({ type: "RegenerateLayer", seed: t.layer_seed + 1 })} />
          </View>
          {t.role !== "kick" ? (
            <>
              <ParamSlider testID="humanize-micro" label="HUMANIZE MICROTIMING (σ)" value={hum.micro} min={0} max={25} format={(v) => `${v.toFixed(1)} ms`} onCommit={(v) => setHum((h) => ({ ...h, micro: +v.toFixed(1) }))} accent={colors.brandSecondary} />
              <ParamSlider testID="humanize-ghost" label="VELOCITY GHOSTING" value={hum.ghost} min={0} max={35} format={(v) => `${v.toFixed(0)}%`} onCommit={(v) => setHum((h) => ({ ...h, ghost: Math.round(v) }))} accent={colors.brandSecondary} />
              <Btn testID="humanize-apply" icon="account-music-outline" label="APPLY HUMANIZATION" onPress={() => op({ type: "ApplyHumanization", micro_ms: hum.micro, ghost_pct: hum.ghost, seed: t.layer_seed })} />
            </>
          ) : <Mono style={st.meta}>Kick is grid-locked (humanization disabled for the fundamental).</Mono>}
        </Panel>
        <Panel title="INSTRUMENT">
          {Object.entries(specs).map(([k, sp]: any) => (
            <ParamSlider key={k} testID={`synth-${k}`} label={k.replace("_", " ").toUpperCase()} value={t.synth[k]} min={sp[0]} max={sp[1]}
              format={(v) => `${v >= 100 ? v.toFixed(0) : v.toFixed(3)} ${sp[3]}`} onCommit={(v) => op({ type: "SetSynthParam", key: k, value: +v.toFixed(4) })} />
          ))}
        </Panel>
        <Panel title="MIXER">
          <ParamSlider testID="mixer-volume" label="VOLUME" value={t.volume} min={-60} max={6} format={(v) => `${v.toFixed(1)} dB`} onCommit={(v) => op({ type: "SetTrackParam", key: "volume", value: +v.toFixed(1) })} />
          <ParamSlider testID="mixer-pan" label="PAN" value={t.pan} min={-1} max={1} format={(v) => (Math.abs(v) < 0.02 ? "C" : v < 0 ? `${Math.round(-v * 50)}L` : `${Math.round(v * 50)}R`)} onCommit={(v) => op({ type: "SetTrackParam", key: "pan", value: +v.toFixed(2) })} accent={colors.brandSecondary} />
          <ParamSlider testID="mixer-send-a" label="SEND A · REVERB" value={t.send_a} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onCommit={(v) => op({ type: "SetTrackParam", key: "send_a", value: +v.toFixed(2) })} />
          {kick && t.role !== "kick" ? (
            <View style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <Mono testID="sidechain-status" style={{ color: sc ? colors.success : colors.muted }}>{sc ? `SIDECHAIN ← ${kick.name} · ${Math.round(sc.depth * 100)}%` : "NO SIDECHAIN"}</Mono>
                <Btn small testID="sidechain-toggle" label={sc ? "REMOVE" : "ADD SC←KICK"} kind={sc ? "danger" : "cyan"}
                  onPress={() => e.applyOps([{ type: "ConfigureSidechain", source: kick.id, target: t.id, enabled: !sc, depth: 0.5 }])} />
              </View>
              {sc ? <ParamSlider testID="sidechain-depth" label="DUCK DEPTH" value={sc.depth} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`}
                onCommit={(v) => e.applyOps([{ type: "ConfigureSidechain", source: kick.id, target: t.id, depth: +v.toFixed(2), release_ms: sc.release_ms }])} /> : null}
            </View>
          ) : null}
        </Panel>
        <Btn testID="track-delete" kind="danger" icon="delete-outline" label="DELETE TRACK (UNDOABLE)" onPress={() => e.applyOps([{ type: "DeleteTrack", track: t.id }]).then((x) => x && router.back())} />
        <Text style={st.meta}>Every edit is a typed operation with revision check; undo from the transport bar.</Text>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  sw: { width: 4, height: 28, borderRadius: radius.sm },
  meta: { color: colors.muted, fontSize: fontSize.sm },
});
