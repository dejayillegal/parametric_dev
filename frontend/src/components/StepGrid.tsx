import React, { memo } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Step } from "@/src/engine";
import { colors, radius } from "@/src/theme";

type Props = { pattern: Step[]; color: string; playStep: number | null; onPress: (i: number) => void; selected?: number | null; testID: string; size?: number };

export const StepGrid = memo(function StepGrid({ pattern, color, playStep, onPress, selected, testID, size = 22 }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.row} testID={testID}>
      {pattern.map((s, i) => {
        const play = playStep === i;
        const alpha = s.on ? 0.35 + 0.65 * (s.vel / 127) : 0;
        return (
          <Pressable key={i} testID={`${testID}-step-${i}`} accessibilityLabel={`Step ${i + 1} ${s.on ? "on" : "off"}`} onPress={() => onPress(i)}
            hitSlop={2}
            style={[st.cell, { width: size, height: size + 14, marginRight: i % 4 === 3 ? 6 : 2, borderColor: selected === i ? colors.onSurface : play ? colors.brandPrimary : colors.border,
              backgroundColor: i % 8 < 4 ? colors.surfaceTertiary : colors.surfaceSecondary }]}>
            {s.on ? <View style={[st.fill, { backgroundColor: color, opacity: alpha, height: `${Math.max(25, (s.vel / 127) * 100)}%` }]} /> : null}
            {s.on && s.ratchet > 1 ? <View style={[st.rat, { backgroundColor: colors.onSurface }]} /> : null}
            {s.on && s.prob < 1 ? <View style={[st.prob, { borderColor: colors.brandSecondary }]} /> : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
});

const st = StyleSheet.create({
  row: { alignItems: "center", paddingRight: 8 },
  cell: { borderWidth: 1, borderRadius: radius.sm, justifyContent: "flex-end", overflow: "hidden" },
  fill: { width: "100%" },
  rat: { position: "absolute", top: 2, left: 2, width: 4, height: 4 },
  prob: { position: "absolute", top: 2, right: 2, width: 6, height: 6, borderWidth: 1, borderRadius: 3 },
});
