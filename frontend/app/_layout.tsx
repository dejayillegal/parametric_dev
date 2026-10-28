import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { LogBox, StyleSheet, Text, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { EngineProvider, useEngine } from "@/src/engine";
import { colors, mono, radius, spacing } from "@/src/theme";

LogBox.ignoreAllLogs(true);

function ToastHost() {
  const { toast } = useEngine();
  const insets = useSafeAreaInsets();
  if (!toast) return null;
  return (
    <View pointerEvents="none" style={[styles.toast, { top: insets.top + 96, borderColor: toast.kind === "err" ? colors.error : colors.success }]}>
      <Text testID="toast-message" style={[styles.toastText, { color: toast.kind === "err" ? colors.error : colors.onSurface }]}>{toast.msg}</Text>
    </View>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <KeyboardProvider>
            <EngineProvider>
              <StatusBar style="light" />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
              <ToastHost />
            </EngineProvider>
          </KeyboardProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  toast: { position: "absolute", left: spacing.md, right: spacing.md, backgroundColor: colors.surfaceInverse, borderWidth: 1, borderRadius: radius.md, padding: spacing.md },
  toastText: { fontFamily: mono, fontSize: 12 },
});
