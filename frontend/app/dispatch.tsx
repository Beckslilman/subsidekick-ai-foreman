import React from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Card, Pill } from "@/src/components/ui";
import { apiGet } from "@/src/api";

type Assignment = { id: string; crew: string; job_id: string; job_name: string; date: string; notes: string };
type CrewGroup = { crew: string; assignments: Assignment[] };
type Dispatch = { date: string; crews: CrewGroup[]; total: number };

export default function DispatchScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const dispatch = useQuery({ queryKey: ["dispatch"], queryFn: () => apiGet<Dispatch>("/dispatch") });

  const dayLabel = dispatch.data?.date
    ? new Date(dispatch.data.date).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })
    : "Tomorrow";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="dispatch-back" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>TOMORROW · {dayLabel.toUpperCase()}</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>Dispatch Board</Text>
        <Text testID="dispatch-total" style={{ color: colors.onSurfaceInverse, opacity: 0.8, fontSize: 13, marginTop: 4 }}>
          {dispatch.data?.total ?? 0} assignment{(dispatch.data?.total ?? 0) === 1 ? "" : "s"} across {dispatch.data?.crews.length ?? 0} crew{(dispatch.data?.crews.length ?? 0) === 1 ? "" : "s"}
        </Text>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={dispatch.isFetching} onRefresh={() => qc.invalidateQueries({ queryKey: ["dispatch"] })} tintColor={colors.brandPrimary} />}
      >
        {dispatch.isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (dispatch.data?.crews.length ?? 0) === 0 ? (
          <View style={{ paddingVertical: spacing.xxl, alignItems: "center" }}>
            <Icon name="account-hard-hat" size={48} color={colors.muted} />
            <Text style={{ color: colors.muted, marginTop: spacing.sm, fontWeight: "700" }}>Nothing dispatched yet.</Text>
          </View>
        ) : (
          dispatch.data?.crews.map((cg) => (
            <View key={cg.crew} testID={`crew-group-${cg.crew.replace(/\s/g, "-").toLowerCase()}`} style={{ marginBottom: spacing.lg }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm }}>
                <View style={{ width: 40, height: 40, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                  <Icon name="account-group" size={22} color={colors.onBrandPrimary} />
                </View>
                <Text style={{ color: colors.onSurface, fontSize: 20, fontWeight: "900" }}>{cg.crew}</Text>
                <View style={{ flex: 1 }} />
                <Pill label={`${cg.assignments.length} ${cg.assignments.length === 1 ? "stop" : "stops"}`} tone="brand" />
              </View>
              {cg.assignments.map((a) => {
                const t = new Date(a.date);
                const timeLabel = t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
                return (
                  <Card key={a.id} style={{ marginBottom: spacing.sm, borderLeftWidth: 6, borderLeftColor: colors.brandPrimary }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>
                          {timeLabel}
                        </Text>
                        <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: 2 }}>
                          {a.job_name}
                        </Text>
                        {a.notes ? (
                          <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.xs }}>{a.notes}</Text>
                        ) : null}
                      </View>
                      <Pressable onPress={() => router.push(`/job/${a.job_id}`)} hitSlop={8}>
                        <Icon name="chevron-right" size={24} color={colors.onSurface} />
                      </Pressable>
                    </View>
                  </Card>
                );
              })}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}
