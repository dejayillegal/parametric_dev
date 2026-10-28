import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useEngine } from "@/src/engine";
import { api } from "@/src/api";
import { Btn, Chip, Icon, Label, Mono, Panel, ParamSlider } from "@/src/ui";
import { colors, fontSize, mono, radius, spacing } from "@/src/theme";

const PARAMS = ["density", "tension", "groove", "distortion", "hypnotic", "width", "variation"];

export default function NewProject() {
  const e = useEngine();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tpl, setTpl] = useState("berghain");
  const t = e.meta?.templates?.[tpl];
  const [seed, setSeed] = useState(String(Math.floor(Math.random() * 99999)));
  const [bpm, setBpm] = useState<number | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [scale, setScale] = useState<string | null>(null);
  const [params, setParams] = useState<Record<string, number>>({});
  const [length, setLength] = useState(64);
  const [busy, setBusy] = useState(false);
  const cur = (k: string) => params[k] ?? t?.params?.[k] ?? 0.5;

  const create = async () => {
    setBusy(true);
    try {
      const p = await api("/projects", {
        body: { template: tpl, seed: parseInt(seed, 10) || 0, bpm: bpm ?? undefined, key: key ?? undefined, scale: scale ?? undefined,
          params: tpl === "empty" ? undefined : { ...t?.params, ...params }, length },
      });
      e.stop();
      e.setProject(p);
      e.setPerf({ section: null, mask: null, repeat: null });
      if (router.canGoBack()) router.back();
      else router.replace("/");
    } catch (err: any) {
      e.notify(err.message, "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}>
        <Pressable testID="new-close" accessibilityLabel="Close" onPress={() => router.back()} style={st.icon}><Icon name="close" size={20} color={colors.onSurface} /></Pressable>
        <Mono style={{ fontSize: fontSize.xl, fontWeight: "700" }}>NEW PROJECT</Mono>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.md, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
        <Label>TEMPLATE</Label>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {Object.entries(e.meta?.templates ?? {}).map(([k, v]: any) => (
            <Chip key={k} testID={`template-${k}`} label={v.name} selected={tpl === k} onPress={() => { setTpl(k); setParams({}); setBpm(null); setKey(null); setScale(null); }} />
          ))}
          <Chip testID="template-empty" label="Empty project" selected={tpl === "empty"} onPress={() => setTpl("empty")} />
        </ScrollView>
        <Panel title="SEED · REPRODUCIBLE">
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <TextInput testID="new-seed-input" value={seed} onChangeText={(v) => setSeed(v.replace(/\D/g, "").slice(0, 9))} keyboardType="number-pad"
              style={st.input} placeholderTextColor={colors.muted} />
            <Btn testID="new-seed-random" icon="dice-5-outline" label="RE-SEED" onPress={() => setSeed(String(Math.floor(Math.random() * 99999)))} />
          </View>
        </Panel>
        {tpl !== "empty" && t ? (
          <>
            <Panel title="TEMPO · KEY">
              <ParamSlider testID="new-bpm" label="BPM" value={bpm ?? t.bpm} min={110} max={150} format={(v) => `${Math.round(v)} BPM`} onCommit={(v) => setBpm(Math.round(v))} />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
                {(e.meta?.keys ?? []).map((k: string) => <Chip key={k} testID={`new-key-${k}`} label={k} selected={(key ?? t.key) === k} onPress={() => setKey(k)} />)}
              </ScrollView>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
                {(e.meta?.scales ?? []).map((k: string) => <Chip key={k} testID={`new-scale-${k}`} label={k} selected={(scale ?? t.scale) === k} onPress={() => setScale(k)} />)}
              </ScrollView>
            </Panel>
            <Panel title="CHARACTER">
              {PARAMS.map((k) => (
                <ParamSlider key={k} testID={`new-param-${k}`} label={k.toUpperCase()} value={cur(k)} min={0} max={1}
                  format={(v) => `${Math.round(v * 100)}%`} onCommit={(v) => setParams((x) => ({ ...x, [k]: +v.toFixed(2) }))} />
              ))}
              <ParamSlider testID="new-length" label="ARRANGEMENT LENGTH" value={length} min={32} max={128} format={(v) => `${Math.round(v / 8) * 8} bars`}
                onCommit={(v) => setLength(Math.round(v / 8) * 8)} />
            </Panel>
          </>
        ) : null}
        <Btn testID="new-create-button" kind="primary" icon="creation" label="GENERATE PROJECT" loading={busy} onPress={create} />
      </KeyboardAwareScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  input: { flex: 1, minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, color: colors.brandSecondary, fontFamily: mono, fontSize: fontSize.lg, paddingHorizontal: spacing.md, backgroundColor: colors.surfaceTertiary },
});
