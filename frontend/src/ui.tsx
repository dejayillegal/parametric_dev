import React, { useRef, useState } from "react";
import { ActivityIndicator, PanResponder, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";
import MaterialDesignIcons from "@react-native-vector-icons/material-design-icons";
import { colors, fontSize, mono, radius, spacing } from "@/src/theme";

export const Icon = MaterialDesignIcons;

export function Mono({ children, style, testID, numberOfLines }: { children: React.ReactNode; style?: any; testID?: string; numberOfLines?: number }) {
  return <Text testID={testID} numberOfLines={numberOfLines} style={[{ fontFamily: mono, color: colors.onSurface, fontSize: fontSize.base }, style]}>{children}</Text>;
}

export function Label({ children, style }: { children: React.ReactNode; style?: any }) {
  return <Text style={[s.label, style]}>{children}</Text>;
}

export function Btn({ label, icon, onPress, testID, kind = "default", disabled, small, style, loading }: {
  label?: string; icon?: any; onPress: () => void; testID: string; kind?: "default" | "primary" | "cyan" | "danger" | "active";
  disabled?: boolean; small?: boolean; style?: ViewStyle; loading?: boolean;
}) {
  const bg = { default: colors.surfaceTertiary, primary: colors.brandPrimary, cyan: colors.brandSecondary, danger: colors.surfaceTertiary, active: colors.brandSecondary }[kind];
  const fg = kind === "primary" || kind === "cyan" || kind === "active" ? colors.onBrandPrimary : kind === "danger" ? colors.error : colors.onSurface;
  return (
    <Pressable testID={testID} accessibilityRole="button" accessibilityLabel={label} disabled={disabled || loading} onPress={onPress}
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: bg, opacity: disabled ? 0.4 : pressed ? 0.7 : 1 }, style]}>
      {loading ? <ActivityIndicator size="small" color={fg} /> : icon ? <Icon name={icon} size={small ? 14 : 16} color={fg} /> : null}
      {label ? <Text style={[s.btnText, { color: fg }, small && { fontSize: fontSize.sm }]}>{label}</Text> : null}
    </Pressable>
  );
}

export function Chip({ label, selected, onPress, testID }: { label: string; selected?: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} accessibilityState={{ selected }}
      style={[s.chip, { borderColor: selected ? colors.brandPrimary : colors.border, backgroundColor: selected ? colors.surfaceInverse : colors.surfaceSecondary }]}>
      <Text style={[s.chipText, { color: selected ? colors.brandPrimary : colors.muted }]}>{label}</Text>
    </Pressable>
  );
}

export function Panel({ title, right, children, testID, style }: { title?: string; right?: React.ReactNode; children: React.ReactNode; testID?: string; style?: any }) {
  return (
    <View testID={testID} style={[s.panel, style]}>
      {title ? (
        <View style={s.panelHead}>
          <Label>{title}</Label>
          {right}
        </View>
      ) : null}
      {children}
    </View>
  );
}

/** Horizontal parameter bar. Drag to change; commits on release. Accessible via increment/decrement. */
export function ParamSlider({ label, value, min, max, onCommit, format, testID, accent = colors.brandPrimary }: {
  label: string; value: number; min: number; max: number; onCommit: (v: number) => void; format?: (v: number) => string; testID: string; accent?: string;
}) {
  const [w, setW] = useState(1);
  const [drag, setDrag] = useState<number | null>(null);
  const x0 = useRef(0);
  const cur = drag ?? value;
  const frac = Math.max(0, Math.min(1, (cur - min) / (max - min || 1)));
  const toVal = (x: number) => min + Math.max(0, Math.min(1, x / w)) * (max - min);
  const latest = useRef(cur);
  const pr = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: (e) => { x0.current = e.nativeEvent.locationX; latest.current = toValRef.current(x0.current); setDrag(latest.current); },
    onPanResponderMove: (_, g) => { latest.current = toValRef.current(x0.current + g.dx); setDrag(latest.current); },
    onPanResponderRelease: () => { commitRef.current(latest.current); setDrag(null); },
    onPanResponderTerminate: () => setDrag(null),
  })).current;
  const toValRef = useRef(toVal);
  toValRef.current = toVal;
  const commitRef = useRef(onCommit);
  commitRef.current = onCommit;
  const step = (max - min) / 20;
  return (
    <View style={s.slider}>
      <View style={s.sliderHead}>
        <Text style={s.sliderLabel} numberOfLines={1}>{label}</Text>
        <Mono testID={`${testID}-value`} style={{ fontSize: fontSize.sm, color: accent }}>{format ? format(cur) : cur.toFixed(2)}</Mono>
      </View>
      <View testID={testID} accessible accessibilityRole="adjustable" accessibilityLabel={label}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(e) => onCommit(Math.max(min, Math.min(max, value + (e.nativeEvent.actionName === "increment" ? step : -step))))}
        onLayout={(e) => setW(e.nativeEvent.layout.width)} style={s.track} {...pr.panHandlers}>
        <View pointerEvents="none" style={[s.fill, { width: `${frac * 100}%`, backgroundColor: accent }]} />
      </View>
    </View>
  );
}

export function Loading({ text }: { text: string }) {
  return (
    <View style={{ padding: spacing.xl, alignItems: "center", gap: spacing.md }}>
      <ActivityIndicator color={colors.brandPrimary} />
      <Mono style={{ color: colors.muted }}>{text}</Mono>
    </View>
  );
}

export const s = StyleSheet.create({
  label: { color: colors.muted, fontSize: fontSize.sm, fontFamily: mono, letterSpacing: 1, textTransform: "uppercase" },
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  btnSmall: { minHeight: 36, paddingHorizontal: spacing.md },
  btnText: { fontFamily: mono, fontSize: fontSize.base, fontWeight: "600" },
  chip: { height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, justifyContent: "center", flexShrink: 0 },
  chipText: { fontFamily: mono, fontSize: fontSize.base },
  panel: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, gap: spacing.md },
  panelHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  slider: { gap: spacing.xs, minWidth: 130 },
  sliderHead: { flexDirection: "row", justifyContent: "space-between" },
  sliderLabel: { color: colors.muted, fontSize: fontSize.sm, flexShrink: 1 },
  track: { height: 28, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, overflow: "hidden" },
  fill: { height: "100%", opacity: 0.85 },
});
