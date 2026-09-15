import React from "react";
import { View, Text, ImageBackground, StyleSheet, Pressable } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing } from "@/src/theme";
import { Button } from "@/src/components/ui";
import { useAuth } from "@/src/auth/auth-context";

export default function LoginScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { signIn, devSignIn } = useAuth();
  const [loading, setLoading] = React.useState(false);

  const handleGoogle = async () => {
    setLoading(true);
    try { await signIn(); } finally { setLoading(false); }
  };
  const handleDemo = async () => {
    setLoading(true);
    try { await devSignIn(); } finally { setLoading(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceInverse }}>
      <ImageBackground
        source={{ uri: "https://images.unsplash.com/photo-1609867271967-a82f85c48531?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200" }}
        style={{ flex: 1 }}
        imageStyle={{ opacity: 0.85 }}
      >
        <LinearGradient
          colors={["transparent", "rgba(9,9,11,0.85)", "#09090B"]}
          style={StyleSheet.absoluteFill}
        />
        <View style={{ flex: 1, justifyContent: "space-between", paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl, paddingHorizontal: spacing.lg }}>
          <View>
            <View style={{ alignSelf: "flex-start", backgroundColor: colors.brandPrimary, paddingHorizontal: 10, paddingVertical: 4 }}>
              <Text style={{ color: colors.onBrandPrimary, fontSize: 12, fontWeight: "900", letterSpacing: 2 }}>AI FOREMAN</Text>
            </View>
          </View>

          <View>
            <Text testID="app-title" style={{ color: "#FFFFFF", fontSize: 56, fontWeight: "900", letterSpacing: -1, lineHeight: 60 }}>SUB{"\n"}SIDEKICK</Text>
            <View style={{ height: 4, width: 80, backgroundColor: colors.brandPrimary, marginTop: spacing.md, marginBottom: spacing.md }} />
            <Text style={{ color: "#FFFFFF", fontSize: 18, fontWeight: "500", lineHeight: 24 }}>
              Your voice-first AI foreman.{"\n"}Talk. Capture. Ship.
            </Text>
          </View>

          <View style={{ gap: spacing.sm }}>
            <Button testID="google-signin-button" label="Sign in with Google" onPress={handleGoogle} variant="primary" loading={loading} />
            <Pressable testID="demo-signin-button" onPress={handleDemo} style={{ minHeight: 44, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: "#FFFFFF", fontSize: 14, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase", textDecorationLine: "underline" }}>
                Or try demo mode
              </Text>
            </Pressable>
          </View>
        </View>
      </ImageBackground>
    </View>
  );
}
