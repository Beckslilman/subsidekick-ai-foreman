import React from "react";
import { View, Text, ScrollView, ActivityIndicator, Pressable, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Card, Pill, SectionHeader } from "@/src/components/ui";
import { apiGet } from "@/src/api";
import { useAuth } from "@/src/auth/auth-context";

type Briefing = { summary: string; active_jobs: number; action_items_count: number; date: string };
type Digest = {
  change_orders: any[]; back_charges: any[]; failed_inspections: any[];
  jobs_count: number; action_required_count: number;
};
type MissedMoney = {
  unsigned_change_orders_total: number; disputed_back_charges_total: number;
  grand_total: number; unsigned_change_orders_count: number; disputed_back_charges_count: number;
};

export default function HomeScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const qc = useQueryClient();

  const briefing = useQuery({ queryKey: ["briefing"], queryFn: () => apiGet<Briefing>("/briefing") });
  const digest = useQuery({ queryKey: ["digest"], queryFn: () => apiGet<Digest>("/digest") });
  const money = useQuery({ queryKey: ["missed-money"], queryFn: () => apiGet<MissedMoney>("/missed-money") });

  const refreshing = briefing.isFetching || digest.isFetching || money.isFetching;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Sticky header */}
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md }}>
          <View>
            <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>SUBSIDEKICK</Text>
            <Text testID="header-user-name" style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>
              {user?.name?.split(" ")[0] || "Foreman"}
            </Text>
          </View>
          <Pressable testID="signout-button" onPress={signOut} hitSlop={12}>
            <Icon name="logout" size={24} color={colors.onSurfaceInverse} />
          </Pressable>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { qc.invalidateQueries(); }} tintColor={colors.brandPrimary} />}
      >
        {/* Missed Money Radar */}
        <View style={{ marginBottom: spacing.md }}>
          <Pressable
            testID="missed-money-card"
            onPress={() => router.push("/(tabs)/digest")}
            style={{
              backgroundColor: colors.brandPrimary,
              borderWidth: 2, borderColor: colors.borderStrong,
              padding: spacing.lg,
              flexDirection: "row", alignItems: "center", gap: spacing.md,
            }}
          >
            <Icon name="cash-multiple" size={44} color={colors.onBrandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.onBrandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>MISSED MONEY RADAR</Text>
              <Text testID="missed-money-total" style={{ color: colors.onBrandPrimary, fontSize: 32, fontWeight: "900", marginTop: 2 }}>
                ${money.data?.grand_total?.toLocaleString?.(undefined, { maximumFractionDigits: 0 }) ?? "0"}
              </Text>
              <Text style={{ color: colors.onBrandPrimary, fontSize: 12, fontWeight: "600", opacity: 0.9 }}>
                {money.data?.unsigned_change_orders_count ?? 0} unsigned CO · {money.data?.disputed_back_charges_count ?? 0} disputed BC · over 7 days
              </Text>
            </View>
            <Icon name="chevron-right" size={28} color={colors.onBrandPrimary} />
          </Pressable>
        </View>

        {/* Quick actions */}
        <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg }}>
          <QuickAction icon="clipboard-text-clock" label="End of Day" testID="quick-eod" onPress={() => router.push("/checkin")} />
          <QuickAction icon="account-hard-hat" label="Dispatch" testID="quick-dispatch" onPress={() => router.push("/dispatch")} />
        </View>

        {/* Morning Briefing */}
        <View style={{ marginBottom: spacing.lg }}>
          <SectionHeader label="Morning Briefing" />
          <Card style={{ backgroundColor: colors.surfaceInverse }}>
            {briefing.isLoading ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : (
              <>
                <Text testID="briefing-summary" style={{ color: colors.onSurfaceInverse, fontSize: 17, fontWeight: "500", lineHeight: 24 }}>
                  {briefing.data?.summary || "No briefing yet."}
                </Text>
                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                  <Pill label={`${briefing.data?.active_jobs ?? 0} Active Jobs`} tone="brand" />
                  <Pill label={`${briefing.data?.action_items_count ?? 0} Action Items`} tone="warning" />
                </View>
              </>
            )}
          </Card>
        </View>

        {/* Action Required */}
        <View>
          <SectionHeader label="Action Required" right={
            <Text style={{ color: colors.brandPrimary, fontSize: 14, fontWeight: "900" }}>
              {digest.data?.action_required_count ?? 0}
            </Text>
          } />

          {digest.data?.change_orders?.slice(0, 3).map((co: any) => (
            <Pressable key={co.id} testID={`co-row-${co.id}`} onPress={() => router.push("/(tabs)/digest")}
              style={{ borderTopWidth: 2, borderColor: colors.borderStrong, paddingVertical: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 72 }}>
              <View style={{ width: 44, height: 44, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}>
                <Icon name="file-document-edit" size={22} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: "800" }} numberOfLines={1}>
                  Change Order — {co.job_name}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 13, marginTop: 2 }} numberOfLines={1}>
                  {co.description}
                </Text>
              </View>
              <Pill label={co.status} tone={co.status === "draft" ? "warning" : "brand"} />
            </Pressable>
          ))}

          {digest.data?.back_charges?.slice(0, 3).map((bc: any) => (
            <Pressable key={bc.id} testID={`bc-row-${bc.id}`} onPress={() => router.push("/(tabs)/digest")}
              style={{ borderTopWidth: 2, borderColor: colors.borderStrong, paddingVertical: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 72 }}>
              <View style={{ width: 44, height: 44, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" }}>
                <Icon name="alert-octagon" size={22} color={colors.onError} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: "800" }} numberOfLines={1}>
                  Back Charge — {bc.job_name}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 13, marginTop: 2 }} numberOfLines={1}>
                  ${bc.amount?.toFixed?.(0) ?? 0} · {bc.description}
                </Text>
              </View>
              <Pill label={bc.status} tone="error" />
            </Pressable>
          ))}

          {digest.data?.failed_inspections?.slice(0, 3).map((ins: any) => (
            <View key={ins.id} testID={`ins-row-${ins.id}`}
              style={{ borderTopWidth: 2, borderColor: colors.borderStrong, paddingVertical: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 72 }}>
              <View style={{ width: 44, height: 44, backgroundColor: colors.warning, alignItems: "center", justifyContent: "center" }}>
                <Icon name="clipboard-alert" size={22} color={colors.onWarning} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: "800" }} numberOfLines={1}>
                  Failed Inspection — {ins.job_name}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 13, marginTop: 2 }} numberOfLines={2}>
                  {ins.inspection_type} · {ins.notes}
                </Text>
              </View>
            </View>
          ))}

          {(digest.data?.action_required_count ?? 0) === 0 && !digest.isLoading && (
            <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
              <Icon name="check-circle" size={40} color={colors.success} />
              <Text style={{ color: colors.muted, marginTop: spacing.sm, fontWeight: "700" }}>All caught up.</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function QuickAction({ icon, label, onPress, testID }: { icon: string; label: string; onPress: () => void; testID: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => ({
        flex: 1, minHeight: 72, borderWidth: 2, borderColor: colors.borderStrong,
        backgroundColor: pressed ? colors.surfaceInverse : colors.surface,
        flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
      })}
    >
      <Icon name={icon as any} size={22} color={colors.onSurface} />
      <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "900", letterSpacing: 1, textTransform: "uppercase" }}>{label}</Text>
    </Pressable>
  );
}
