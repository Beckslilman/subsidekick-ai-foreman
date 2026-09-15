import { Tabs } from "expo-router";
import { View } from "react-native";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme } from "@/src/theme";

export default function TabsLayout() {
  const { colors } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopWidth: 2,
          borderTopColor: colors.borderStrong,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase" },
        tabBarItemStyle: { alignSelf: "center" },
      }}
    >
      <Tabs.Screen name="index" options={{
        title: "Briefing",
        tabBarIcon: ({ color, size }) => <Icon name="bullhorn" size={size} color={color} />,
      }} />
      <Tabs.Screen name="voice" options={{
        title: "Talk",
        tabBarIcon: ({ color, size }) => <Icon name="microphone" size={size} color={color} />,
      }} />
      <Tabs.Screen name="jobs" options={{
        title: "Jobs",
        tabBarIcon: ({ color, size }) => <Icon name="hard-hat" size={size} color={color} />,
      }} />
      <Tabs.Screen name="digest" options={{
        title: "Office",
        tabBarIcon: ({ color, size }) => <Icon name="clipboard-list" size={size} color={color} />,
      }} />
    </Tabs>
  );
}
