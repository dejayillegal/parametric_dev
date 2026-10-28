import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { api, API } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { Btn, Chip, Label, Loading, Mono, Panel } from "@/src/ui";
import { usesNativeTabs } from "@/src/navigation";
import { colors, fontSize, radius, spacing } from "@/src/theme";

function PlanCard({ plan, mode, claude, applied, onChanged }: { plan: any; mode: string; claude: boolean; applied: boolean; onChanged: () => void }) {
  const e = useEngine();
  const router = useRouter();
  const [open, setOpen] = useState<"ops" | "manual" | null>(null);
  const [explain, setExplain] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const p = e.project!;
  const preview = (original: boolean) => e.playUrl(`${API}/projects/${p.id}/plans/${plan.id}/preview.wav?mode=${encodeURIComponent(mode)}${original ? "&original=true" : ""}`);
  const apply = async () => {
    setLoading("apply");
    try {
      const r = await api(`/projects/${p.id}/plans/${plan.id}/apply`, { body: { base_revision: p.revision, mode } });
      e.setProject(r.project);
      e.notify(`Applied: ${r.applied.join("; ")}`);
      onChanged();
    } catch (err: any) {
      e.notify(err.message, "err");
    } finally {
      setLoading(null);
    }
  };
  const doExplain = async () => {
    setLoading("explain");
    try {
      const r = await api("/ai/explain", { body: { consent: true, plan } });
      setExplain(r.text);
    } catch (err: any) {
      setExplain(`Cloud explanation unavailable: ${err.message}`);
    } finally {
      setLoading(null);
    }
  };
  const id = plan.id;
  return (
    <View testID={`plan-card-${id}`} style={st.card}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: spacing.sm }}>
        <Mono style={{ fontWeight: "700", flex: 1 }}>{plan.title}</Mono>
        <Mono style={{ color: applied ? colors.success : colors.muted, fontSize: fontSize.sm }}>{applied ? "APPLIED" : plan.kind.toUpperCase()}</Mono>
      </View>
      <Mono style={st.meta}>bars {plan.start_bar + 1}–{plan.end_bar} · conf {Math.round(plan.confidence * 100)}% · risk {plan.risk} · {plan.finding}</Mono>
      <Text style={st.body}>{plan.rationale} → {plan.expected_outcome}</Text>
      {explain ? <Text testID={`plan-explain-text-${id}`} style={[st.body, { color: colors.brandSecondary }]}>Claude: {explain}</Text> : null}
      <Mono style={st.meta}>{plan.compatibility}</Mono>
      <View style={st.actions}>
        <Btn small testID={`plan-preview-${id}`} icon="play" label="PREVIEW" kind="cyan" onPress={() => preview(false)} />
        <Btn small testID={`plan-preview-original-${id}`} icon="compare" label="A/B ORIG" onPress={() => preview(true)} />
        <Btn small testID={`plan-locate-${id}`} icon="crosshairs-gps" label="LOCATE" onPress={() => router.push(`/arrange?from=${plan.start_bar}&to=${plan.end_bar}`)} />
        <Btn small testID={`plan-inspect-${id}`} icon="code-json" label="PARAMS" kind={open === "ops" ? "active" : "default"} onPress={() => setOpen(open === "ops" ? null : "ops")} />
        <Btn small testID={`plan-manual-${id}`} icon="format-list-numbered" label="MANUAL" kind={open === "manual" ? "active" : "default"} onPress={() => setOpen(open === "manual" ? null : "manual")} />
        {claude ? <Btn small testID={`plan-explain-${id}`} icon="chat-processing-outline" label="EXPLAIN" loading={loading === "explain"} onPress={doExplain} /> : null}
        <Btn small testID={`plan-reject-${id}`} icon="close" label="REJECT" kind="danger" onPress={async () => {
          const r = ((await storage.getItem("rejected_plans", "[]" as string)) as string) ?? "[]";
          await storage.setItem("rejected_plans", JSON.stringify([...JSON.parse(r), id]));
          onChanged();
        }} />
        <Btn small testID={`plan-apply-${id}`} icon="check" label="ACCEPT & APPLY" kind="primary" loading={loading === "apply"} onPress={apply} />
      </View>
      {open === "ops" ? (
        <View testID={`plan-ops-${id}`} style={st.code}>
          {plan.operations.map((o: any, i: number) => <Mono key={i} style={{ fontSize: fontSize.sm }}>{JSON.stringify(o)}</Mono>)}
          <Mono style={[st.meta, { marginTop: spacing.sm }]}>Undo: {plan.undo}</Mono>
        </View>
      ) : null}
      {open === "manual" ? (
        <View testID={`plan-manual-steps-${id}`} style={st.code}>
          {plan.manual_steps.map((m: string, i: number) => <Mono key={i} style={{ fontSize: fontSize.sm }}>{i + 1}. {m}</Mono>)}
        </View>
      ) : null}
    </View>
  );
}

export default function AI() {
  const e = useEngine();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [mode, setMode] = useState("Hybrid");
  const [claude, setClaude] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);
  const p = e.project;

  useEffect(() => { storage.getItem("claude_consent", false).then((v) => setClaude(!!v)); }, []);
  const analyze = useCallback(async () => {
    if (!p) return;
    setLoading(true);
    try {
      const [r, rej] = await Promise.all([api(`/projects/${p.id}/analysis?mode=${encodeURIComponent(mode)}`), storage.getItem("rejected_plans", "[]" as string)]);
      setRes(r);
      setRejected(JSON.parse((rej as string) ?? "[]"));
    } catch (err: any) {
      e.notify(err.message, "err");
    } finally {
      setLoading(false);
    }
  }, [p, mode, e]);
  useEffect(() => { if (res && p && res.plans?.[0]?.revision !== p.revision) analyze(); }, [p?.revision]); // eslint-disable-line react-hooks/exhaustive-deps

  const appliedIds = new Set((res?.applied_plans ?? []).map((a: any) => a.plan_id));
  const visible = (res?.plans ?? []).filter((x: any) => !rejected.includes(x.id));
  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}><Mono style={{ fontSize: fontSize.xl, fontWeight: "700" }}>AI ENGINE</Mono><Mono style={st.meta}>rule-based planner · typed ops</Mono></View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: bottomChrome + spacing.xl }}>
        {!p ? (
          <View testID="ai-empty" style={{ gap: spacing.md }}>
            <Mono>No context. Open or create a project first.</Mono>
            <Btn testID="ai-new-project" kind="primary" label="NEW PROJECT" onPress={() => router.push("/new")} />
          </View>
        ) : (
          <>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
              {(e.meta?.ai_modes ?? []).map((m: string) => <Chip key={m} testID={`ai-mode-${m.replace(/\W+/g, "-").toLowerCase()}`} label={m} selected={mode === m} onPress={() => setMode(m)} />)}
            </ScrollView>
            <Panel>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Mono style={{ fontWeight: "700" }}>Claude explanations</Mono>
                  <Text style={st.meta}>Sends only the selected plan summary (no audio, no project file) to Claude when you tap EXPLAIN.</Text>
                </View>
                <Switch testID="ai-claude-toggle" value={claude} onValueChange={(v) => { setClaude(v); storage.setItem("claude_consent", v); }}
                  trackColor={{ true: colors.brandSecondary, false: colors.brandTertiary }} thumbColor={colors.onSurface} />
              </View>
            </Panel>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Btn testID="ai-analyze-button" kind="primary" icon="radar" label={`ANALYZE ${p.name.toUpperCase()}`} onPress={analyze} loading={loading} style={{ flex: 1 }} />
              {rejected.length ? <Btn testID="ai-restore-rejected" small label={`RESTORE ${rejected.length}`} onPress={async () => { await storage.setItem("rejected_plans", "[]"); setRejected([]); }} /> : null}
            </View>
            {loading && !res ? <Loading text="Generating techno completion plan..." /> : null}
            {res ? (
              <>
                <Panel title="FEATURES" testID="ai-features">
                  <Mono style={st.meta}>{res.features.analysis_basis}</Mono>
                  <Mono style={{ fontSize: fontSize.sm }}>roles {res.features.roles.join(", ") || "none"} · key {res.features.key} · 4/4 kick {res.features.kick_four_on_floor ? "yes" : "no"}</Mono>
                  <Mono style={{ fontSize: fontSize.sm }}>sections {res.features.sections.join(" › ") || "none"}</Mono>
                  <Mono style={{ fontSize: fontSize.sm }}>sidechained {res.features.sidechain_targets.join(", ") || "none"} · automation {res.features.automation_lanes.join(", ") || "none"}</Mono>
                </Panel>
                <Label>MISSINGNESS GRAPH · {visible.length} PLANS</Label>
                {visible.length === 0 ? <Mono testID="ai-no-plans" style={st.meta}>No outstanding issues found by the rule set.</Mono> : null}
                {visible.map((pl: any) => <PlanCard key={pl.id} plan={pl} mode={mode} claude={claude} applied={appliedIds.has(pl.id)} onChanged={analyze} />)}
                {res.applied_plans?.length ? (
                  <Panel title="APPLIED (UNDO = TRANSPORT ↶)">
                    {res.applied_plans.map((a: any) => <Mono key={a.plan_id + a.revision} style={st.meta}>r{a.revision} · {a.label}</Mono>)}
                  </Panel>
                ) : null}
              </>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  meta: { color: colors.muted, fontSize: fontSize.sm },
  body: { color: colors.onSurface, fontSize: fontSize.base, lineHeight: 17 },
  card: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  code: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, gap: spacing.xs },
});
