import React, { useCallback, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { api, API } from "@/src/api";
import { uploadForm } from "@/src/utils/upload";
import { Btn, Icon, Label, Loading, Mono, Panel } from "@/src/ui";
import { usesNativeTabs } from "@/src/navigation";
import { colors, fontSize, radius, spacing } from "@/src/theme";

export default function Projects() {
  const e = useEngine();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [projects, setProjects] = useState<any[] | null>(null);
  const [sets, setSets] = useState<any[] | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([api("/projects"), api("/als")]);
      setProjects(a);
      setSets(b);
    } catch (err: any) {
      e.notify(err.message, "err");
    }
  }, [e]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const importAls = async () => {
    setError(null);
    const r = await DocumentPicker.getDocumentAsync({ type: "*/*", copyToCacheDirectory: true });
    if (r.canceled) return;
    const f = r.assets[0];
    setImporting(true);
    try {
      const res = await uploadForm(`${API}/als/import`, { files: { file: { uri: f.uri, name: f.name, mimeType: "application/octet-stream" } } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Import failed");
      router.push(`/als/${data.id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };
  const demo = async () => {
    setImporting(true);
    try {
      const d = await api("/als/demo", { method: "POST" });
      router.push(`/als/${d.id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}><Mono style={{ fontSize: fontSize.xl, fontWeight: "700" }}>PROJECTS</Mono></View>
      <ScrollView refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: bottomChrome + spacing.xl }}>
        <Panel title="PARAMETRIC PROJECTS" right={<Btn small testID="projects-new" kind="primary" icon="plus" label="NEW" onPress={() => router.push("/new")} />}>
          {projects === null ? <Loading text="Loading projects..." /> : projects.length === 0 ? <Mono style={st.muted}>No projects yet.</Mono> :
            projects.map((p) => (
              <View key={p.id} style={[st.row, e.project?.id === p.id && { borderColor: colors.brandPrimary }]}>
                <Pressable testID={`project-open-${p.id}`} style={{ flex: 1, minHeight: 44, justifyContent: "center" }}
                  onPress={() => e.openProject(p.id).then(() => router.navigate("/"))}>
                  <Mono style={{ fontWeight: "700" }}>{p.name}</Mono>
                  <Mono style={st.muted}>{p.bpm} BPM · {p.key} {p.scale} · seed {p.seed} · {p.track_count} trk · r{p.revision}</Mono>
                </Pressable>
                <Pressable testID={`project-duplicate-${p.id}`} accessibilityLabel="Duplicate" style={st.icon}
                  onPress={() => api(`/projects/${p.id}/duplicate`, { method: "POST" }).then(load)}><Icon name="content-copy" size={18} color={colors.muted} /></Pressable>
                <Pressable testID={`project-delete-${p.id}`} accessibilityLabel="Delete" style={st.icon}
                  onPress={() => api(`/projects/${p.id}`, { method: "DELETE" }).then(() => { if (e.project?.id === p.id) { e.stop(); e.setProject(null); } load(); })}>
                  <Icon name="delete-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))}
        </Panel>
        <Panel title="ABLETON LIVE SETS (.ALS) · READ / INSPECT">
          <Text style={st.muted}>Files are uploaded to your Parametric workspace for parsing only when you tap import. Max 15 MB.</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Btn testID="als-import-button" kind="cyan" icon="file-upload-outline" label="IMPORT .ALS" loading={importing} onPress={importAls} style={{ flex: 1 }} />
            <Btn testID="als-demo-button" icon="flask-outline" label="TEST FIXTURE" onPress={demo} disabled={importing} style={{ flex: 1 }} />
          </View>
          {error ? <Mono testID="als-import-error" style={{ color: colors.error }}>✕ {error}</Mono> : null}
          {sets === null ? null : sets.length === 0 ? <Mono style={st.muted}>No Live Sets imported.</Mono> :
            sets.map((s) => (
              <View key={s.id} style={st.row}>
                <Pressable testID={`als-open-${s.id}`} style={{ flex: 1, minHeight: 44, justifyContent: "center" }} onPress={() => router.push(`/als/${s.id}`)}>
                  <Mono numberOfLines={1} style={{ fontWeight: "700" }}>{s.filename}</Mono>
                  <Mono style={st.muted}>{s.summary?.version?.creator} · {s.summary?.tempo} BPM · {s.summary?.counts?.tracks} trk · {s.summary?.counts?.clips} clips</Mono>
                </Pressable>
                <Pressable testID={`als-delete-${s.id}`} accessibilityLabel="Delete" style={st.icon} onPress={() => api(`/als/${s.id}`, { method: "DELETE" }).then(load)}>
                  <Icon name="delete-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))}
          <Label>TEST FIXTURE = original synthetic Live-11-style set generated by Parametric (not authored in Ableton)</Label>
        </Panel>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  muted: { color: colors.muted, fontSize: fontSize.sm },
  row: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingLeft: spacing.md, backgroundColor: colors.surfaceTertiary },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
});
