import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, API, downloadAndShare } from "@/src/api";
import { Btn, Chip, Icon, Label, Loading, Mono, Panel } from "@/src/ui";
import { colors, fontSize, mono, radius, spacing } from "@/src/theme";

const TABS = ["Overview", "Tracks", "Sidechains", "Diagnostics", "Export"];
const statusColor = (s: string) => (s === "pass" || s.startsWith("confirmed") ? colors.success : s === "fail" || s === "invalid" ? colors.error : s === "warn" ? colors.warning : colors.muted);
const bar = (beats: number | null, ts: number[] | null) => (beats === null || beats === undefined ? "-" : (beats / (ts?.[0] ?? 4) + 1).toFixed(2));

function TrackNode({ t, byId, ts, depth }: { t: any; byId: Record<string, any>; ts: number[]; depth: number }) {
  const [open, setOpen] = useState(false);
  return (
    <View>
      <Pressable testID={`als-track-${t.id}`} onPress={() => setOpen(!open)} style={[st.node, { marginLeft: depth * 14 }]}>
        <Icon name={t.kind === "group" ? "folder-outline" : t.kind === "audio" ? "waveform" : t.kind === "return" ? "keyboard-return" : "piano"} size={16} color={colors.brandPrimary} />
        <View style={{ flex: 1 }}>
          <Mono style={{ fontWeight: "700" }}>{t.name} <Text style={st.meta}>#{t.id} {t.kind}</Text></Mono>
          <Mono style={st.meta}>{t.clips.length} clips · {t.devices.length} dev · → {t.output ?? "?"} · {t.volume_db ?? "?"} dB{t.active ? "" : " · OFF"}</Mono>
        </View>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
      </Pressable>
      {open ? (
        <View testID={`als-track-detail-${t.id}`} style={[st.detail, { marginLeft: depth * 14 + 8 }]}>
          {t.devices.map((d: any, i: number) => (
            <Mono key={i} style={{ fontSize: fontSize.sm, color: d.known ? colors.onSurface : colors.warning }}>
              ▸ {d.name}{d.plugin ? ` (${d.plugin})` : ""} · {d.kind}{d.known ? "" : " · UNKNOWN/OPAQUE (preserved, read-only)"}{d.on ? "" : " · bypassed"} · {d.preview_status}
              {d.children?.length ? ` · ${d.children.length} nested` : ""}
            </Mono>
          ))}
          {t.clips.map((c: any, i: number) => (
            <Mono key={`c${i}`} style={{ fontSize: fontSize.sm }}>
              ◼ {c.scope} {c.type} «{c.name}» bar {bar(c.start, ts)}→{bar(c.end, ts)}{c.type === "midi" ? ` · ${c.note_count} notes` : ` · ${c.sample}`}{c.loop_on ? " · loop" : ""}
            </Mono>
          ))}
          {t.envelopes.map((en: any, i: number) => (
            <Mono key={`e${i}`} style={{ fontSize: fontSize.sm, color: en.resolved ? colors.brandSecondary : colors.error }}>
              ∿ automation {en.target ? `${en.target.device ?? ""} ${en.target.param}` : `UNRESOLVED ${en.pointee}`} · {en.points.length} pts {en.points.slice(0, 4).map((p: any) => `b${bar(p.time, ts)}=${p.value}`).join(" ")}
            </Mono>
          ))}
          {t.take_lane_clips ? <Mono style={st.meta}>take lanes: {t.take_lane_clips} clips</Mono> : null}
        </View>
      ) : null}
      {t.children.map((cid: string) => byId[cid] ? <TrackNode key={cid} t={byId[cid]} byId={byId} ts={ts} depth={depth + 1} /> : null)}
    </View>
  );
}

export default function AlsInspector() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState("Overview");
  const [tempo, setTempo] = useState("");
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [report, setReport] = useState<any>(null);
  const [compiling, setCompiling] = useState(false);

  const load = useCallback(() => api(`/als/${id}`).then(setD).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const compile = async (ops: any[]) => {
    setCompiling(true);
    try { setReport(await api(`/als/${id}/compile`, { body: { ops } })); load(); }
    catch (e: any) { setReport({ report: { status: "blocked", error: e.message } }); }
    finally { setCompiling(false); }
  };

  if (err) return <View style={[st.root, { padding: spacing.xl, paddingTop: insets.top + spacing.xl }]}><Mono testID="als-error" style={{ color: colors.error }}>{err}</Mono></View>;
  if (!d) return <View style={[st.root, { paddingTop: insets.top }]}><Loading text="Parsing ALS XML structure..." /></View>;
  const s = d.summary;
  const byId = Object.fromEntries(s.tracks.map((t: any) => [t.id, t]));
  const roots = s.tracks.filter((t: any) => !byId[t.group_id]);
  const fails = s.invariants.filter((i: any) => i.status === "fail");
  const ops: any[] = [];
  if (tempo && parseFloat(tempo) !== s.tempo) ops.push({ type: "SetTempo", bpm: parseFloat(tempo) });
  if (renameId && renameTo.trim()) ops.push({ type: "RenameTrack", track_id: renameId, name: renameTo.trim() });
  const r = report?.report;

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}>
        <Pressable testID="als-back" accessibilityLabel="Back" onPress={() => router.back()} style={st.icon}><Icon name="arrow-left" size={20} color={colors.onSurface} /></Pressable>
        <View style={{ flex: 1 }}>
          <Mono numberOfLines={1} style={{ fontWeight: "700" }}>{d.filename}</Mono>
          <Mono style={st.meta}>{s.version.creator} · adapter {s.version.adapter} · {d.container} · {(d.size / 1024).toFixed(1)} KB</Mono>
        </View>
      </View>
      <View style={{ height: 56, borderBottomWidth: 1, borderColor: colors.border }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.md, alignItems: "center" }}>
          {TABS.map((t) => <Chip key={t} testID={`als-tab-${t.toLowerCase()}`} label={t === "Diagnostics" && fails.length ? `${t} (${fails.length})` : t} selected={tab === t} onPress={() => setTab(t)} />)}
        </ScrollView>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        {tab === "Overview" ? (
          <>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <Panel style={{ flex: 1 }} title="TEMPO"><Mono testID="als-tempo" style={{ fontSize: 28, fontWeight: "700", color: colors.brandPrimary }}>{s.tempo}</Mono>
                <Mono style={st.meta}>{s.tempo_automated ? "tempo automated" : "constant tempo"}</Mono></Panel>
              <Panel style={{ flex: 1 }} title="TIME SIG"><Mono testID="als-timesig" style={{ fontSize: 28, fontWeight: "700" }}>{s.time_signature?.join("/") ?? "?"}</Mono>
                <Mono style={st.meta}>{s.key ? `key ${s.key.root} ${s.key.scale}` : "key: not stored in set"}</Mono></Panel>
            </View>
            <Panel title="CONTENTS" testID="als-counts">
              <Mono style={{ fontSize: fontSize.sm }}>{s.counts.tracks} tracks ({s.returns} returns) · {s.counts.clips} clips · {s.counts.notes} notes · {s.counts.devices} devices · {s.counts.envelopes} envelopes</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>arrangement end: bar {bar(s.arrangement_length_beats, s.time_signature)} · loop {s.loop ? `${s.loop.on ? "on" : "off"} bar ${bar(s.loop.start, s.time_signature)} len ${s.loop.length} beats` : "n/a"}</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>locators: {s.locators.map((l: any) => `${l.name}@${bar(l.time, s.time_signature)}`).join(", ") || "none"}</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>scenes: {s.scenes.join(", ") || "none"}</Mono>
              <Mono style={{ fontSize: fontSize.sm }}>XML: {s.counts.elements} elements · {s.counts.attributes} attributes</Mono>
            </Panel>
            <Panel title="COMPATIBILITY (THIS VERSION)">
              {Object.entries(s.version.capabilities).map(([k, v]: any) => <Mono key={k} style={{ fontSize: fontSize.sm }}>{k}: {Array.isArray(v) ? v.join(", ") || "none" : String(v)}</Mono>)}
              <Text style={st.meta}>Browser/phone preview of native Ableton instruments is not available; this is read & inspect.</Text>
            </Panel>
          </>
        ) : null}
        {tab === "Tracks" ? (
          <Panel title="TRACK TREE (REAL GROUP HIERARCHY)" testID="als-track-tree">
            {roots.map((t: any) => <TrackNode key={t.id} t={t} byId={byId} ts={s.time_signature} depth={0} />)}
            {s.master ? <Mono style={st.meta}>MASTER: {s.master.devices.map((x: any) => x.name).join(" → ") || "no devices"}</Mono> : null}
          </Panel>
        ) : null}
        {tab === "Sidechains" ? (
          <>
            <Panel title="DETECTED FROM DEVICE ROUTING (NOT NAMES)" testID="als-sidechains">
              {s.sidechains.length === 0 ? <Mono style={st.meta}>No sidechain routings found.</Mono> : s.sidechains.map((x: any, i: number) => (
                <View key={i} style={st.scRow}>
                  <Mono style={{ color: statusColor(x.status), fontWeight: "700", fontSize: fontSize.sm }}>{x.status.toUpperCase()}</Mono>
                  <Mono style={{ fontSize: fontSize.sm, flex: 1 }}>{x.source ?? x.route} ─▶ {x.device} on {x.destination}</Mono>
                </View>
              ))}
            </Panel>
            <Label>RECOMMENDATIONS (MANUAL STEPS · NATIVE INSERTION NOT VERIFIED)</Label>
            {d.plans.map((pl: any) => (
              <Panel key={pl.id} testID={`als-plan-${pl.id}`} title={pl.kind.toUpperCase()}>
                <Mono style={{ fontWeight: "700" }}>{pl.title}</Mono>
                <Text style={st.meta}>{pl.finding} · {pl.compatibility}</Text>
                {pl.manual_steps.map((m: string, i: number) => <Mono key={i} style={{ fontSize: fontSize.sm }}>{i + 1}. {m}</Mono>)}
              </Panel>
            ))}
          </>
        ) : null}
        {tab === "Diagnostics" ? (
          <>
            <View testID="als-invariants" style={st.term}>
              {s.invariants.map((i: any) => (
                <Mono key={i.id} style={{ fontSize: fontSize.sm, color: statusColor(i.status) }}>[{i.status.toUpperCase().padEnd(4)}] {i.id} {i.title} — {i.detail}</Mono>
              ))}
            </View>
            <Panel title={`ASSETS · ${s.assets.length}`} testID="als-assets">
              {s.assets.length === 0 ? <Mono style={st.meta}>No audio file references.</Mono> : s.assets.map((a: any, i: number) => (
                <Mono key={i} style={{ fontSize: fontSize.sm, color: colors.warning }}>{a.track}/{a.clip}: {a.path} — {a.status}</Mono>
              ))}
            </Panel>
            <Panel title="PRESERVED UNKNOWN STRUCTURES">
              <Mono style={{ fontSize: fontSize.sm }}>{s.unknown_top_level.join(", ") || "none"}</Mono>
            </Panel>
          </>
        ) : null}
        {tab === "Export" ? (
          <>
            <Panel title="NO-OP ROUND TRIP">
              <Text style={st.meta}>Returns the original bytes unchanged (verified by SHA-256).</Text>
              <Btn testID="als-noop-export" icon="sync" label="COMPILE NO-OP" loading={compiling} onPress={() => compile([])} />
            </Panel>
            <Panel title="TYPED PATCH (SetTempo · RenameTrack)">
              <TextInput testID="als-tempo-input" value={tempo} onChangeText={setTempo} placeholder={`Tempo (current ${s.tempo})`} placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={st.input} />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
                {s.tracks.map((t: any) => <Chip key={t.id} testID={`als-rename-pick-${t.id}`} label={t.name} selected={renameId === t.id} onPress={() => { setRenameId(t.id); setRenameTo(t.name); }} />)}
              </ScrollView>
              {renameId ? <TextInput testID="als-rename-input" value={renameTo} onChangeText={setRenameTo} placeholder="New track name" placeholderTextColor={colors.muted} style={st.input} /> : null}
              <Btn testID="als-compile-button" kind="primary" icon="cog-play-outline" label={`COMPILE ${ops.length} OP(S) + VALIDATE`} disabled={!ops.length} loading={compiling} onPress={() => compile(ops)} />
            </Panel>
            {r ? (
              <Panel title="EXPORT REPORT" testID="als-report">
                <Mono testID="als-report-status" style={{ fontWeight: "700", color: r.status === "blocked" ? colors.error : colors.success }}>STATUS: {r.status}</Mono>
                {r.error ? <Mono style={{ color: colors.error }}>✕ {r.error}</Mono> : null}
                {r.detail ? <Mono style={{ fontSize: fontSize.sm }}>{r.detail}</Mono> : null}
                {r.sha256_in ? <Mono style={st.meta}>sha in {r.sha256_in.slice(0, 16)} · out {r.sha256_out.slice(0, 16)}</Mono> : null}
                {r.lines_changed !== undefined ? <Mono style={{ fontSize: fontSize.sm }}>{r.lines_changed} source line(s) changed · gzip re-read {r.gzip_roundtrip_ok ? "OK" : "FAILED"} · unexpected: {r.unexpected_changes?.join(", ") || "none"}</Mono> : null}
                {r.diff?.map((x: any, i: number) => (
                  <View key={i} style={st.term}>
                    <Mono style={{ fontSize: fontSize.sm, color: colors.muted }}>L{x.line} {x.what}</Mono>
                    <Mono style={{ fontSize: fontSize.sm, color: colors.error }}>- {x.old}</Mono>
                    <Mono style={{ fontSize: fontSize.sm, color: colors.success }}>+ {x.new}</Mono>
                  </View>
                ))}
                {r.invariants?.filter((i: any) => i.status !== "pass").map((i: any) => <Mono key={i.id} style={{ fontSize: fontSize.sm, color: statusColor(i.status) }}>{i.id} {i.status}: {i.detail}</Mono>)}
                <Mono style={{ fontSize: fontSize.sm, color: colors.warning }}>Native reopen: {r.native_reopen}</Mono>
                {report.downloadable ? <Btn testID="als-download-export" kind="cyan" icon="download" label={`DOWNLOAD ${report.filename}`} onPress={() => downloadAndShare(`${API}/als/exports/${report.id}/download`, report.filename)} /> : null}
              </Panel>
            ) : null}
          </>
        ) : null}
      </KeyboardAwareScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  meta: { color: colors.muted, fontSize: fontSize.sm },
  node: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44, borderBottomWidth: 1, borderColor: colors.border },
  detail: { gap: spacing.xs, padding: spacing.sm, backgroundColor: colors.surface, borderLeftWidth: 1, borderColor: colors.brandPrimary },
  scRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  term: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, gap: spacing.xs },
  input: { minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, color: colors.onSurface, fontFamily: mono, paddingHorizontal: spacing.md, backgroundColor: colors.surfaceTertiary },
});
