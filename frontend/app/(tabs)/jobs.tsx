import React from "react";
import { View, Text, FlatList, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Pill } from "@/src/components/ui";
import { apiGet } from "@/src/api";

type Job = { id: string; code?: string; name: string; gc: string; address: string; status: string; crew: string; crew_size: number; progress: number; working_on: string; next_milestone: string };

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
          contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xxxl, paddingTop: spacing.sm }}
          renderItem={({ item }) => (
            <Pressable testID={`job-row-${item.id}`} onPress={() => router.push(`/job/${item.id}`)}
              style={{ borderBottomWidth: 2, borderColor: colors.borderStrong, padding: spacing.lg, flexDirection: "row", alignItems: "flex-start", gap: spacing.md }}>
              <View style={{ width: 52, height: 52, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center" }}>
                <Text style={{ color: colors.brandPrimary, fontWeight: "900", fontSize: 14, letterSpacing: 1 }}>{item.code || item.name.slice(0, 3).toUpperCase()}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900" }} numberOfLines={1}>{item.name}</Text>
                <Text style={{ color: colors.muted, fontSize: 13, marginTop: 2, fontWeight: "600" }}>{item.address}</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs, alignItems: "center", flexWrap: "wrap" }}>
                  <Pill label={item.status} tone={item.status === "active" ? "success" : "neutral"} />
                  <Text style={{ color: colors.onSurface, fontSize: 12, fontWeight: "600" }}>{item.crew} · {item.crew_size}</Text>
                </View>
                {item.working_on ? <Text style={{ color: colors.onSurface, fontSize: 13, marginTop: spacing.xs, fontWeight: "600" }}>{item.working_on}</Text> : null}
                {item.next_milestone ? <Text style={{ color: colors.brandPrimary, fontSize: 12, fontWeight: "900", marginTop: 2 }}>{item.next_milestone}</Text> : null}
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm }}>
                  <View style={{ flex: 1, height: 6, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.borderStrong }}>
                    <View style={{ width: `${item.progress}%`, height: "100%", backgroundColor: colors.brandPrimary }} />
                  </View>
                  <Text style={{ color: colors.onSurface, fontWeight: "900", fontSize: 12 }}>{item.progress}%</Text>
                </View>
              </View>
              <Icon name="chevron-right" size={24} color={colors.onSurface} />
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
