import { Tabs } from "expo-router";
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
        tabBarStyle: { backgroundColor: colors.surface, borderTopWidth: 2, borderTopColor: colors.borderStrong },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase" },
        tabBarItemStyle: { alignSelf: "center" },
      }}
    >
      <Tabs.Screen name="index" options={{
        title: "Digest",
        tabBarIcon: ({ color, size }) => <Icon name="view-dashboard-variant" size={size} color={color} />,
      }} />
      <Tabs.Screen name="inbox" options={{
        title: "Inbox",
        tabBarIcon: ({ color, size }) => <Icon name="tray-full" size={size} color={color} />,
      }} />
      <Tabs.Screen name="jobs" options={{
        title: "Jobs",
        tabBarIcon: ({ color, size }) => <Icon name="hard-hat" size={size} color={color} />,
      }} />
      <Tabs.Screen name="calls" options={{
        title: "Calls",
        tabBarIcon: ({ color, size }) => <Icon name="phone-in-talk" size={size} color={color} />,
      }} />
    </Tabs>
  );
}
