import React from "react";
import { Pressable, StyleSheet, Text, View, ViewStyle, TextStyle, ActivityIndicator } from "react-native";
import { useTheme, spacing } from "../theme";

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  testID?: string;
};

export function Button({ label, onPress, variant = "primary", disabled, loading, style, testID }: ButtonProps) {
  const { colors } = useTheme();
  const bg =
    variant === "primary" ? colors.brandPrimary
      : variant === "danger" ? colors.error
      : colors.surface;
  const fg =
    variant === "primary" ? colors.onBrandPrimary
      : variant === "danger" ? colors.onError
      : colors.onSurface;
  const borderColor = colors.borderStrong;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        {
          backgroundColor: pressed ? colors.surfaceInverse : bg,
          borderColor,
          borderWidth: 2,
          minHeight: 56,
          paddingHorizontal: spacing.lg,
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "row",
          opacity: disabled ? 0.5 : 1,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={{ color: fg, fontSize: 18, fontWeight: "800", letterSpacing: 0.5, textTransform: "uppercase" }}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const { colors } = useTheme();
  return (
    <View style={[{ backgroundColor: colors.surface, borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md }, style]}>
      {children}
    </View>
  );
}

export function Pill({ label, tone = "neutral", testID }: { label: string; tone?: "neutral" | "brand" | "success" | "warning" | "error"; testID?: string }) {
  const { colors } = useTheme();
  const map = {
    neutral: { bg: colors.surfaceTertiary, fg: colors.onSurfaceTertiary },
    brand: { bg: colors.brandPrimary, fg: colors.onBrandPrimary },
    success: { bg: colors.success, fg: colors.onSuccess },
    warning: { bg: colors.warning, fg: colors.onWarning },
    error: { bg: colors.error, fg: colors.onError },
  } as const;
  const { bg, fg } = map[tone];
  return (
    <View testID={testID} style={{ backgroundColor: bg, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1.5, borderColor: colors.borderStrong }}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase" }}>{label}</Text>
    </View>
  );
}

export function SectionHeader({ label, right }: { label: string; right?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md }}>
      <Text style={{ fontSize: 14, fontWeight: "900", color: colors.onSurface, letterSpacing: 2, textTransform: "uppercase" }}>{label}</Text>
      {right}
    </View>
  );
}
