import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { api, API, downloadAndShare } from "@/src/api";
import { Btn, Chip, Icon, Label, Mono, Panel } from "@/src/ui";
import { colors, fontSize, radius, spacing } from "@/src/theme";

const PX = 10; // px per bar

function LaneView({ lane, total }: { lane: any; total: number }) {
  const spec = { "master.cutoff": [200, 20000], "stabs.cutoff": [200, 12000], "rumble.cutoff": [40, 600], "master.volume": [-36, 0] }[lane.target as string] ?? [0, 1];
  const log = lane.target.endsWith("cutoff");
  const norm = (v: number) => (log ? Math.log(v / spec[0]) / Math.log(spec[1] / spec[0]) : (v - spec[0]) / (spec[1] - spec[0]));
  return (
    <View style={{ width: total * PX, height: 40, backgroundColor: colors.surfaceTertiary }}>
      {lane.points.map((pt: any, i: number) => (
        <View key={i} style={{ position: "absolute", left: pt.bar * PX - 3, bottom: norm(pt.value) * 34, width: 6, height: 6, borderRadius: 3, backgroundColor: lane.source === "ai" ? colors.brandSecondary : colors.brandPrimary }} />
      ))}
    </View>
  );
}

export default function Arrange() {
  const e = useEngine();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { from, to } = useLocalSearchParams<{ from?: string; to?: string }>();
  const [bits, setBits] = useState(24);
  const [sr, setSr] = useState(44100);
  const [scope, setScope] = useState<string>("arrangement");
  const [normalize, setNormalize] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [measuring, setMeasuring] = useState(false);
  const p = e.project;
  if (!p) {
    return (
      <View style={[st.root, { padding: spacing.xl, paddingTop: insets.top + spacing.xl, gap: spacing.md }]}>
        <Mono>No project loaded.</Mono>
        <Btn testID="arrange-back" label="BACK" onPress={() => router.back()} />
      </View>
    );
  }
  const total = p.sections.reduce((a, s) => a + s.bars, 0);
  const starts = p.sections.map((_, i) => p.sections.slice(0, i).reduce((a, s) => a + s.bars, 0));
  const hl = from !== undefined ? [parseFloat(from), parseFloat(to ?? from)] : null;
  const sd = 60 / p.bpm / 4;
  const playBar = e.override?.includes("mode=arrangement") ? e.position / (sd * 16) : null;
  const q = () => {
    const base = scope === "loop" ? "mode=loop&bars=4" : "mode=arrangement";
    const tr = scope.startsWith("trk_") ? `&track=${scope}` : "";
    return `${base}${tr}&sr=${sr}&bits=${bits}`;
  };
  const measure = async () => {
    setMeasuring(true);
    try { setStats(await api(`/projects/${p.id}/render/stats?${q().replace(/&bits=\d+/, "")}&bits=${bits}`)); }
    catch (err: any) { e.notify(err.message, "err"); }
    finally { setMeasuring(false); }
  };
  const lanePreset = (kind: string) => {
    const bi = p.sections.findIndex((s) => s.name.startsWith("Breakdown"));
    const b0 = bi >= 0 ? starts[bi] : 0;
    const b1 = bi >= 0 ? b0 + p.sections[bi].bars : Math.min(8, total);
    const ops: Record<string, any> = {
      riser: { type: "SetAutomationLane", target: "master.cutoff", curve: "exp", points: [{ bar: Math.max(0, b0 - 0.01), value: 20000 }, { bar: b0, value: 400 }, { bar: b1 - 0.25, value: 12000 }, { bar: b1, value: 20000 }] },
      stabs: { type: "SetAutomationLane", target: "stabs.cutoff", curve: "s", points: [{ bar: 0, value: 500 }, { bar: b0, value: 600 }, { bar: b1, value: 5000 }, { bar: total, value: 1200 }] },
      rumble: { type: "SetAutomationLane", target: "rumble.cutoff", curve: "linear", points: [{ bar: 0, value: 80 }, { bar: total / 2, value: 260 }, { bar: total, value: 120 }] },
      fade: { type: "SetAutomationLane", target: "master.volume", curve: "linear", points: [{ bar: Math.max(0, total - 8), value: 0 }, { bar: total, value: -36 }] },
    };
    e.applyOps([ops[kind]]);
  };

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}>
        <Pressable testID="arrange-back" accessibilityLabel="Back" onPress={() => router.back()} style={st.icon}><Icon name="arrow-left" size={20} color={colors.onSurface} /></Pressable>
        <Mono style={{ fontWeight: "700", fontSize: fontSize.lg, flex: 1 }}>ARRANGEMENT · {total} BARS</Mono>
        <Pressable testID="arrange-play" onPress={() => (e.override ? e.stop() : e.playUrl(`${API}/projects/${p.id}/render.wav?mode=arrangement&rev=${p.revision}`))} style={st.icon}>
          <Icon name={e.override ? "stop" : "play"} size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        {hl ? <Mono testID="arrange-locate-banner" style={{ color: colors.brandSecondary }}>Located: bars {hl[0] + 1}–{hl[1]} (highlighted)</Mono> : null}
        <Panel title="TIMELINE · TAP CELL TO TOGGLE TRACK IN SECTION">
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: "row" }}>
              <View style={{ width: 84 }}>
                <View style={{ height: 36 }} />
                {p.tracks.map((t) => <Mono key={t.id} numberOfLines={1} style={[st.lab, { color: t.color }]}>{t.name}</Mono>)}
              </View>
              <View>
                <View style={{ flexDirection: "row", height: 36 }}>
                  {p.sections.map((s, i) => (
                    <View key={i} style={[st.secHead, { width: s.bars * PX }]}>
                      <Text numberOfLines={1} style={st.secT}>{s.name}</Text>
                      <Text style={st.barT}>{starts[i] + 1}</Text>
                    </View>
                  ))}
                </View>
                {p.tracks.map((t) => (
                  <View key={t.id} style={{ flexDirection: "row", height: 28 }}>
                    {p.sections.map((s, i) => {
                      const on = s.active.includes(t.id);
                      return (
                        <Pressable key={i} testID={`arr-cell-${i}-${t.id}`} onPress={() => e.applyOps([{ type: "ToggleSectionTrack", section: i, track: t.id }])}
                          style={[st.cell, { width: s.bars * PX }, on && { backgroundColor: t.color, opacity: 0.75 }]} />
                      );
                    })}
                  </View>
                ))}
                {hl ? <View pointerEvents="none" style={[st.hl, { left: hl[0] * PX, width: Math.max(2, (hl[1] - hl[0]) * PX) }]} /> : null}
                {playBar !== null ? <View pointerEvents="none" testID="arrange-playhead" style={[st.playhead, { left: playBar * PX }]} /> : null}
              </View>
            </View>
          </ScrollView>
          <Label>GENERATE SECTION (APPENDS · UNDOABLE)</Label>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
            {["Intro", "Build", "Breakdown", "Drop", "Outro"].map((k) => <Chip key={k} testID={`gen-section-${k.toLowerCase()}`} label={`+ ${k}`} onPress={() => e.applyOps([{ type: "GenerateArrangementSection", kind: k, bars: 8 }])} />)}
          </ScrollView>
        </Panel>
        <Panel title="AUTOMATION LANES">
          {p.automation.length === 0 ? <Mono style={st.meta}>No lanes.</Mono> : p.automation.map((ln: any) => (
            <View key={ln.id} style={{ gap: spacing.xs }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Mono testID={`lane-${ln.target}`} style={{ fontSize: fontSize.sm }}>{ln.target} · {ln.curve} · {ln.source} · {ln.points.length} pts</Mono>
                <Btn small testID={`lane-delete-${ln.target}`} icon="delete-outline" kind="danger" onPress={() => e.applyOps([{ type: "DeleteAutomationLane", target: ln.target }])} />
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}><LaneView lane={ln} total={total} /></ScrollView>
              <Mono style={st.meta}>{ln.points.map((pt: any) => `b${(pt.bar + 1).toFixed(2)}=${pt.value}`).join(" · ")}</Mono>
            </View>
          ))}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
            <Chip testID="lane-preset-riser" label="+ Master filter riser" onPress={() => lanePreset("riser")} />
            <Chip testID="lane-preset-stabs" label="+ Stab cutoff S-curve" onPress={() => lanePreset("stabs")} />
            <Chip testID="lane-preset-rumble" label="+ Rumble cutoff sweep" onPress={() => lanePreset("rumble")} />
            <Chip testID="lane-preset-fade" label="+ Outro fade" onPress={() => lanePreset("fade")} />
          </ScrollView>
        </Panel>
        <Panel title="RENDER · WAV">
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
            <Chip testID="render-scope-arrangement" label="Arrangement" selected={scope === "arrangement"} onPress={() => setScope("arrangement")} />
            <Chip testID="render-scope-loop" label="Loop 4 bars" selected={scope === "loop"} onPress={() => setScope("loop")} />
            {p.tracks.map((t) => <Chip key={t.id} testID={`render-scope-${t.id}`} label={`Stem ${t.name}`} selected={scope === t.id} onPress={() => setScope(t.id)} />)}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
            {[16, 24, 32].map((b) => <Chip key={b} testID={`render-bits-${b}`} label={b === 32 ? "32f" : `${b}-bit`} selected={bits === b} onPress={() => setBits(b)} />)}
            {[44100, 48000].map((r) => <Chip key={r} testID={`render-sr-${r}`} label={`${r / 1000} kHz`} selected={sr === r} onPress={() => setSr(r)} />)}
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Switch testID="render-normalize" value={normalize} onValueChange={setNormalize} trackColor={{ true: colors.brandSecondary, false: colors.brandTertiary }} thumbColor={colors.onSurface} />
            <Mono style={st.meta}>Normalize to -1 dBFS peak (dither: TPDF on 16/24-bit)</Mono>
          </View>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Btn testID="render-measure" icon="chart-bell-curve" label="MEASURE" loading={measuring} onPress={measure} style={{ flex: 1 }} />
            <Btn testID="render-download" kind="primary" icon="download" label="EXPORT WAV" style={{ flex: 1 }}
              onPress={() => downloadAndShare(`${API}/projects/${p.id}/render.wav?${q()}&normalize=${normalize}&download=true`, `${p.name.replace(/\W+/g, "_")}_${scope}_${bits}.wav`).catch((err) => e.notify(err.message, "err"))} />
          </View>
          {stats ? (
            <View testID="render-stats" style={st.code}>
              <Mono style={{ fontSize: fontSize.sm }}>{stats.bars} bars · {stats.seconds.toFixed(2)} s · {stats.frames} frames · render {stats.render_ms} ms</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>peak {stats.peak_dbfs} dBFS · RMS {stats.rms_dbfs} dBFS · integrated {stats.lufs_integrated ?? "n/a"} LUFS (BS.1770)</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>correlation {stats.stereo_correlation} · clipped {stats.clipped_samples} · limiter GR max {stats.max_gain_reduction_db} dB</Mono>
              <Mono style={{ fontSize: fontSize.sm, color: colors.success }}>header ✓ fmt {stats.wav_header_check.format} · {stats.wav_header_check.channels} ch · {stats.wav_header_check.sr} Hz · {stats.wav_header_check.bits}-bit</Mono>
            </View>
          ) : null}
          <Text style={st.meta}>Stems render the track pre-master-bus with its sends; Ableton native devices are not part of this engine.</Text>
        </Panel>
        <Panel title="MIDI">
          <Btn testID="export-midi" icon="piano" label={`EXPORT MIDI (${total} BARS, SMF TYPE 1)`} onPress={() => downloadAndShare(`${API}/projects/${p.id}/midi.mid?bars=${Math.min(256, total)}`, `${p.name.replace(/\W+/g, "_")}.mid`).catch((err) => e.notify(err.message, "err"))} />
        </Panel>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  meta: { color: colors.muted, fontSize: fontSize.sm },
  lab: { height: 28, fontSize: fontSize.sm, lineHeight: 28 },
  secHead: { borderLeftWidth: 1, borderColor: colors.borderStrong, paddingLeft: 2, justifyContent: "center" },
  secT: { color: colors.onSurface, fontSize: 9, fontWeight: "700" },
  barT: { color: colors.muted, fontSize: 9 },
  cell: { height: 24, marginTop: 2, borderLeftWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  hl: { position: "absolute", top: 0, bottom: 0, backgroundColor: colors.brandSecondary, opacity: 0.25 },
  playhead: { position: "absolute", top: 0, bottom: 0, width: 2, backgroundColor: colors.brandPrimary },
  code: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, gap: spacing.xs },
});
