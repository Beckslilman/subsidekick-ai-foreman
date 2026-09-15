import React, { useState, useEffect } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl, Image, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Pill, Card } from "@/src/components/ui";
import { apiGet, apiPatch, API_BASE } from "@/src/api";
import { getToken } from "@/src/auth/token-store";

type ChangeOrder = { id: string; job_name: string; description: string; amount?: number; status: string; created_at: string; photo_url?: string | null };
type BackCharge = { id: string; job_name: string; description: string; amount: number; status: string; created_at: string; photo_url?: string | null };
type Inspection = { id: string; job_name: string; inspection_type: string; result: string; notes: string };
type Digest = {
  change_orders: ChangeOrder[]; back_charges: BackCharge[]; failed_inspections: Inspection[];
  jobs_count: number; action_required_count: number;
};

const TABS = ["Change Orders", "Back Charges", "Inspections"] as const;

export default function DigestScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Change Orders");
  const [token, setToken] = useState<string | null>(null);
  const qc = useQueryClient();
  const digest = useQuery({ queryKey: ["digest"], queryFn: () => apiGet<Digest>("/digest") });

  useEffect(() => { (async () => setToken(await getToken()))(); }, []);

  function photoSrc(url: string): { uri: string; headers?: Record<string, string> } {
    if (Platform.OS === "web") {
      return { uri: `${API_BASE}${url}?token=${encodeURIComponent(token || "")}` };
    }
    return { uri: `${API_BASE}${url}`, headers: token ? { Authorization: `Bearer ${token}` } : undefined };
  }

  async function approve(id: string) {
    await apiPatch(`/change-orders/${id}`, { status: "approved" });
    qc.invalidateQueries();
  }
  async function reject(id: string) {
    await apiPatch(`/change-orders/${id}`, { status: "rejected" });
    qc.invalidateQueries();
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
          <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>ADMIN</Text>
          <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Office Digest</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: spacing.md, height: 56, alignItems: "center" }}>
          {TABS.map((t) => (
            <Pressable
              key={t}
              testID={`digest-tab-${t.replace(/\s/g, "-").toLowerCase()}`}
              onPress={() => setTab(t)}
              style={{
                height: 36, paddingHorizontal: spacing.md, justifyContent: "center",
                backgroundColor: tab === t ? colors.brandPrimary : "transparent",
                borderWidth: 2, borderColor: tab === t ? colors.brandPrimary : colors.onSurfaceInverse,
                flexShrink: 0,
              }}
            >
              <Text style={{ color: tab === t ? colors.onBrandPrimary : colors.onSurfaceInverse, fontWeight: "900", letterSpacing: 1, fontSize: 12, textTransform: "uppercase" }}>
                {t}
              </Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={digest.isFetching} onRefresh={() => qc.invalidateQueries({ queryKey: ["digest"] })} tintColor={colors.brandPrimary} />}
      >
        {digest.isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : tab === "Change Orders" ? (
          (digest.data?.change_orders ?? []).length === 0 ? (
            <Empty label="No change orders to review." />
          ) : (
            (digest.data?.change_orders ?? []).map((co) => (
              <Card key={co.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.brandPrimary }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900" }}>{co.job_name}</Text>
                    <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "700", marginTop: 2, letterSpacing: 1 }}>
                      CHANGE ORDER · {new Date(co.created_at).toLocaleDateString()}
                    </Text>
                  </View>
                  <Pill label={co.status} tone={co.status === "draft" ? "warning" : co.status === "approved" ? "success" : "brand"} />
                </View>
                <Text style={{ marginTop: spacing.sm, color: colors.onSurface, fontSize: 15 }}>{co.description}</Text>
                {co.photo_url ? (
                  <Image testID={`co-photo-${co.id}`} source={photoSrc(co.photo_url)} style={{ marginTop: spacing.sm, width: "100%", height: 200, borderWidth: 2, borderColor: colors.borderStrong, resizeMode: "cover" }} />
                ) : null}
                {co.amount != null && (
                  <Text style={{ marginTop: spacing.sm, color: colors.onSurface, fontSize: 24, fontWeight: "900" }}>
                    ${co.amount.toFixed(2)}
                  </Text>
                )}
                {(co.status === "draft" || co.status === "pending") && (
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
                )}
              </Card>
            ))
          )
        ) : tab === "Back Charges" ? (
          (digest.data?.back_charges ?? []).length === 0 ? (
            <Empty label="No back charges." />
          ) : (
            (digest.data?.back_charges ?? []).map((bc) => (
              <Card key={bc.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.error }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900" }}>{bc.job_name}</Text>
                    <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "700", marginTop: 2, letterSpacing: 1 }}>
                      BACK CHARGE · {new Date(bc.created_at).toLocaleDateString()}
                    </Text>
                  </View>
                  <Pill label={bc.status} tone="error" />
                </View>
                <Text style={{ marginTop: spacing.sm, color: colors.onSurface, fontSize: 15 }}>{bc.description}</Text>
                {bc.photo_url ? (
                  <Image testID={`bc-photo-${bc.id}`} source={photoSrc(bc.photo_url)} style={{ marginTop: spacing.sm, width: "100%", height: 200, borderWidth: 2, borderColor: colors.borderStrong, resizeMode: "cover" }} />
                ) : null}
                <Text style={{ marginTop: spacing.sm, color: colors.error, fontSize: 24, fontWeight: "900" }}>
                  -${bc.amount.toFixed(2)}
                </Text>
              </Card>
            ))
          )
        ) : (
          (digest.data?.failed_inspections ?? []).length === 0 ? (
            <Empty label="All inspections passing." />
          ) : (
            (digest.data?.failed_inspections ?? []).map((ins) => (
              <Card key={ins.id} style={{ marginBottom: spacing.md, borderLeftWidth: 6, borderLeftColor: colors.warning }}>
                <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900" }}>{ins.job_name}</Text>
                <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "700", marginTop: 2, letterSpacing: 1 }}>
                  {ins.inspection_type.toUpperCase()} · FAILED
                </Text>
                <Text style={{ marginTop: spacing.sm, color: colors.onSurface, fontSize: 15 }}>{ins.notes}</Text>
              </Card>
            ))
          )
        )}
      </ScrollView>
    </View>
  );
}

function Empty({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ paddingVertical: spacing.xxl, alignItems: "center" }}>
      <Icon name="check-circle" size={48} color={colors.success} />
      <Text style={{ color: colors.muted, marginTop: spacing.sm, fontWeight: "700" }}>{label}</Text>
    </View>
  );
}
