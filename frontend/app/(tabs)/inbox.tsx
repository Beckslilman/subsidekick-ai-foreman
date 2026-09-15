import React, { useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Pill, Card } from "@/src/components/ui";
import { apiGet, apiPatch } from "@/src/api";

type Digest = {
  change_orders: any[]; back_charges: any[]; schedule_changes: any[]; failed_inspections: any[];
  jobs: any[]; action_required_count: number; money_at_risk: number;
};

const TABS = ["All", "Change Orders", "Back Charges", "Schedule", "Inspections"] as const;

export default function InboxScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<(typeof TABS)[number]>("All");
  const qc = useQueryClient();
  const digest = useQuery({ queryKey: ["digest"], queryFn: () => apiGet<Digest>("/digest") });

  async function approve(id: string) { await apiPatch(`/change-orders/${id}`, { status: "approved" }); qc.invalidateQueries(); }
  async function reject(id: string) { await apiPatch(`/change-orders/${id}`, { status: "rejected" }); qc.invalidateQueries(); }
  async function resolveBc(id: string) { await apiPatch(`/back-charges/${id}`, { status: "resolved" }); qc.invalidateQueries(); }
  async function confirmSc(id: string) { await apiPatch(`/schedule-changes/${id}`, { status: "confirmed" }); qc.invalidateQueries(); }

  const showCos = tab === "All" || tab === "Change Orders";
  const showBcs = tab === "All" || tab === "Back Charges";
  const showScs = tab === "All" || tab === "Schedule";
  const showIns = tab === "All" || tab === "Inspections";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
          <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>DRAFTS & RECORDS</Text>
          <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Field Inbox</Text>
          <Text style={{ color: colors.onSurfaceInverse, opacity: 0.7, fontSize: 12, marginTop: 2 }}>
            {digest.data?.action_required_count ?? 0} items · ${(digest.data?.money_at_risk ?? 0).toLocaleString()} at risk
          </Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: spacing.md, height: 56, alignItems: "center" }}>
          {TABS.map((t) => (
            <Pressable key={t} testID={`inbox-tab-${t.replace(/\s/g, "-").toLowerCase()}`} onPress={() => setTab(t)}
              style={{
                height: 36, paddingHorizontal: spacing.md, justifyContent: "center",
                backgroundColor: tab === t ? colors.brandPrimary : "transparent",
                borderWidth: 2, borderColor: tab === t ? colors.brandPrimary : colors.onSurfaceInverse,
                flexShrink: 0,
              }}>
              <Text style={{ color: tab === t ? colors.onBrandPrimary : colors.onSurfaceInverse, fontWeight: "900", letterSpacing: 1, fontSize: 12, textTransform: "uppercase" }}>{t}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={digest.isFetching} onRefresh={() => qc.invalidateQueries({ queryKey: ["digest"] })} tintColor={colors.brandPrimary} />}>
        {digest.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (
          <>
            {showCos && (digest.data?.change_orders ?? []).map((co: any) => (
              <Card key={co.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.brandPrimary }}>
                <TypeBadge label="CHANGE ORDER" color={colors.brandPrimary} />
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: spacing.sm }}>{co.title || co.description}</Text>
                <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600", marginTop: 2 }}>
                  {co.job_name} · {co.reported_by}{co.reported_by_phone ? " · " + co.reported_by_phone : ""}
                </Text>
                <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm, lineHeight: 20 }}>{co.description}</Text>
                {co.amount != null && (
                  <Text style={{ color: colors.onSurface, fontSize: 24, fontWeight: "900", marginTop: spacing.sm }}>${co.amount.toLocaleString()}</Text>
                )}
                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                  <Pressable testID={`co-approve-${co.id}`} onPress={() => approve(co.id)}
                    style={{ flex: 1, minHeight: 48, backgroundColor: colors.success, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                    <Text style={{ color: colors.onSuccess, fontWeight: "900", letterSpacing: 1 }}>APPROVE</Text>
                  </Pressable>
                  <Pressable testID={`co-reject-${co.id}`} onPress={() => reject(co.id)}
                    style={{ flex: 1, minHeight: 48, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                    <Text style={{ color: colors.onSurface, fontWeight: "900", letterSpacing: 1 }}>REJECT</Text>
                  </Pressable>
                </View>
                <DraftFooter />
              </Card>
            ))}
            {showBcs && (digest.data?.back_charges ?? []).map((bc: any) => (
              <Card key={bc.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.error }}>
                <TypeBadge label="BACK CHARGE" color={colors.error} />
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: spacing.sm }}>{bc.title || bc.description}</Text>
                <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600", marginTop: 2 }}>
                  {bc.job_name} · {bc.reported_by}{bc.reported_by_phone ? " · " + bc.reported_by_phone : ""}
                </Text>
                <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm, lineHeight: 20 }}>{bc.description}</Text>
                <Text style={{ color: colors.error, fontSize: 24, fontWeight: "900", marginTop: spacing.sm }}>-${bc.amount.toLocaleString()}</Text>
                <Pressable testID={`bc-resolve-${bc.id}`} onPress={() => resolveBc(bc.id)}
                  style={{ minHeight: 48, marginTop: spacing.md, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                  <Text style={{ color: colors.onSurfaceInverse, fontWeight: "900", letterSpacing: 1 }}>MARK RESOLVED</Text>
                </Pressable>
                <DraftFooter />
              </Card>
            ))}
            {showScs && (digest.data?.schedule_changes ?? []).map((sc: any) => (
              <Card key={sc.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.warning }}>
                <TypeBadge label="SCHEDULE CHANGE" color={colors.warning} textColor="#000" />
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: spacing.sm }}>{sc.description}</Text>
                <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600", marginTop: 2 }}>
                  {sc.job_name} · {sc.reported_by}
                </Text>
                <Pressable testID={`sc-confirm-${sc.id}`} onPress={() => confirmSc(sc.id)}
                  style={{ minHeight: 48, marginTop: spacing.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                  <Text style={{ color: colors.onBrandPrimary, fontWeight: "900", letterSpacing: 1 }}>NOTIFY & CONFIRM</Text>
                </Pressable>
                <DraftFooter />
              </Card>
            ))}
            {showIns && (digest.data?.failed_inspections ?? []).map((ins: any) => (
              <Card key={ins.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.warning }}>
                <TypeBadge label="FAILED INSPECTION" color={colors.warning} textColor="#000" />
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: spacing.sm }}>{ins.job_name}</Text>
                <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600", marginTop: 2 }}>{ins.inspection_type} · FAILED</Text>
                <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm }}>{ins.notes}</Text>
              </Card>
            ))}
            {(digest.data?.action_required_count ?? 0) === 0 && (
              <View style={{ paddingVertical: spacing.xxl, alignItems: "center" }}>
                <Icon name="check-circle" size={48} color={colors.success} />
                <Text style={{ color: colors.muted, marginTop: spacing.sm, fontWeight: "700" }}>Inbox zero. Crews are humming.</Text>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function TypeBadge({ label, color, textColor }: { label: string; color: string; textColor?: string }) {
  return (
    <View style={{ alignSelf: "flex-start", backgroundColor: color, paddingHorizontal: 8, paddingVertical: 3 }}>
      <Text style={{ color: textColor || "#FFFFFF", fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>{label}</Text>
    </View>
  );
}

function DraftFooter() {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm }}>
      <View style={{ width: 8, height: 8, backgroundColor: colors.warning }} />
      <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 1 }}>DRAFT ONLY — NOT SENT</Text>
    </View>
  );
}
