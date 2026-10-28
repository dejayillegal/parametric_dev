// Design tokens (dark only) from /app/design_guidelines.json.
import { useMemo } from "react";
import { Appearance, Platform, StyleSheet } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  surface: "#0B0D10",
  onSurface: "#E6E8EB",
  surfaceSecondary: "#12161B",
  onSurfaceSecondary: "#E6E8EB",
  surfaceTertiary: "#181D23",
  onSurfaceTertiary: "#E6E8EB",
  surfaceInverse: "#202630",
  onSurfaceInverse: "#E6E8EB",
  muted: "#8C949F",
  brand: "#F59E0B",
  onBrand: "#0B0D10",
  brandPrimary: "#F59E0B",
  onBrandPrimary: "#0B0D10",
  brandSecondary: "#06B6D4",
  onBrandSecondary: "#0B0D10",
  brandTertiary: "#2A3038",
  onBrandTertiary: "#E6E8EB",
  success: "#22C55E",
  onSuccess: "#0B0D10",
  warning: "#F59E0B",
  onWarning: "#0B0D10",
  error: "#EF4444",
  onError: "#0B0D10",
  info: "#06B6D4",
  onInfo: "#0B0D10",
  border: "#2A3038",
  borderStrong: "#8C949F",
  divider: "#2A3038",
};

export type ThemeColors = typeof dark;
export const colors = dark;
export const defaultScheme: ColorScheme = "dark";
export const themes: { light?: ThemeColors; dark: ThemeColors } = { dark };

export const spacing = { xs: 2, sm: 4, md: 8, lg: 12, xl: 16, xxl: 24, xxxl: 32 };
export const radius = { sm: 2, md: 4, lg: 8, pill: 999 };
export const fontSize = { sm: 10, base: 12, lg: 14, xl: 16, xxl: 20 };
export const mono = Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" });

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}
setColorScheme?.("dark");

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  return { scheme: "dark", colors: dark };
}

export function makeStyles<T extends Record<string, any>>(factory: (colors: ThemeColors) => T): () => T {
  return function useStyles(): T {
    const { colors: c } = useTheme();
    return useMemo(() => StyleSheet.create(factory(c)), [c]);
  };
}
