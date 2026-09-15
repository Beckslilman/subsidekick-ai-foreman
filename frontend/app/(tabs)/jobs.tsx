import React from "react";
import { View, Text, FlatList, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Pill } from "@/src/components/ui";
import { apiGet } from "@/src/api";

type Job = { id: string; name: string; gc: string; address: string; status: string; crew: string; progress: number };

export default function JobsScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => apiGet<Job[]>("/jobs") });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>ACTIVE</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Jobs & Crews</Text>
      </View>

      {jobs.isLoading ? (
        <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brandPrimary} />
      ) : (
        <FlatList
          data={jobs.data ?? []}
          keyExtractor={(j) => j.id}
          refreshControl={<RefreshControl refreshing={jobs.isFetching} onRefresh={() => qc.invalidateQueries({ queryKey: ["jobs"] })} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xxxl }}
          renderItem={({ item }) => (
            <Pressable
              testID={`job-row-${item.id}`}
              onPress={() => router.push(`/job/${item.id}`)}
              style={{ borderBottomWidth: 2, borderColor: colors.borderStrong, padding: spacing.lg, minHeight: 96 }}
            >
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={{ color: colors.onSurface, fontSize: 20, fontWeight: "900", flex: 1 }} numberOfLines={1}>{item.name}</Text>
                <Icon name="chevron-right" size={24} color={colors.onSurface} />
              </View>
              <Text style={{ color: colors.muted, fontSize: 14, marginTop: 4, fontWeight: "600" }}>
                {item.gc} · {item.crew || "Unassigned"}
              </Text>
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm, alignItems: "center" }}>
                <Pill label={item.status} tone={item.status === "active" ? "success" : "neutral"} />
                <View style={{ flex: 1, height: 6, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.borderStrong }}>
                  <View style={{ width: `${item.progress}%`, height: "100%", backgroundColor: colors.brandPrimary }} />
                </View>
                <Text style={{ color: colors.onSurface, fontWeight: "900", fontSize: 12 }}>{item.progress}%</Text>
              </View>
            </Pressable>
          )}
          ListEmptyComponent={
            <View style={{ padding: spacing.xl, alignItems: "center" }}>
              <Icon name="hard-hat" size={48} color={colors.muted} />
              <Text style={{ color: colors.muted, marginTop: spacing.sm, fontWeight: "700" }}>No active jobs.</Text>
            </View>
          }
        />
      )}
    </View>
  );
}
