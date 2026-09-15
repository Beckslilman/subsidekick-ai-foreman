import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  // Surfaces
  surface: "#FFFFFF",
  onSurface: "#09090B",
  surfaceSecondary: "#F4F4F5",
  onSurfaceSecondary: "#09090B",
  surfaceTertiary: "#E4E4E7",
  onSurfaceTertiary: "#18181B",
  surfaceInverse: "#09090B",
  onSurfaceInverse: "#FFFFFF",
  muted: "#71717A",

  // Brand — Industrial Orange
  brand: "#FF5A00",
  onBrand: "#FFFFFF",
  brandPrimary: "#FF5A00",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E04F00",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#FFF1EA",
  onBrandTertiary: "#A13800",

  // Status
  success: "#166534",
  onSuccess: "#FFFFFF",
  warning: "#EAB308",
  onWarning: "#000000",
  error: "#DC2626",
  onError: "#FFFFFF",
  info: "#0F172A",
  onInfo: "#FFFFFF",

  // Lines
  border: "#E4E4E7",
  borderStrong: "#09090B",
  divider: "#E4E4E7",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme);
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}

export const spacing = {
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
};

export const radius = {
  sm: 0,
  md: 4,
  lg: 8,
  pill: 999,
};

export const fonts = {
  // System fonts, bold weights used to emulate Barlow/IBM Plex feel
  display: undefined as string | undefined, // rely on fontWeight
  text: undefined as string | undefined,
};
