import React from "react";
import { View, Text, ScrollView, ActivityIndicator, Pressable, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Card, Pill } from "@/src/components/ui";
import { apiGet } from "@/src/api";
import { useAuth } from "@/src/auth/auth-context";

type Job = { id: string; code?: string; name: string; gc: string; address: string; crew: string; crew_size: number; working_on: string; next_milestone: string };
type Digest = {
  change_orders: any[]; back_charges: any[]; schedule_changes: any[]; failed_inspections: any[];
  jobs: Job[]; action_required_count: number; money_at_risk: number;
};
type Briefing = { summary: string; active_jobs: number; drafts_pending: number; back_charges_open: number; schedule_changes_open: number };

export default function DigestScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const qc = useQueryClient();

  const digest = useQuery({ queryKey: ["digest"], queryFn: () => apiGet<Digest>("/digest") });
  const briefing = useQuery({ queryKey: ["briefing"], queryFn: () => apiGet<Briefing>("/briefing") });

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
  const firstName = user?.name?.split(" ")[0] ?? "boss";

  const refreshing = digest.isFetching || briefing.isFetching;
  const potentialValue = digest.data?.money_at_risk ?? 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Sticky header */}
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md }}>
          <View>
            <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>SUBSIDEKICK</Text>
            <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Office Dashboard</Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
            <Pressable testID="settings-button" onPress={() => router.push("/settings")} hitSlop={12}>
              <Icon name="cog" size={22} color={colors.onSurfaceInverse} />
            </Pressable>
            <Pressable testID="signout-button" onPress={signOut} hitSlop={12}>
              <Icon name="logout" size={24} color={colors.onSurfaceInverse} />
            </Pressable>
          </View>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => qc.invalidateQueries()} tintColor={colors.brandPrimary} />}
      >
        {/* Hero */}
        <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>{today}</Text>
        <Text testID="hero-greeting" style={{ color: colors.onSurface, fontSize: 40, fontWeight: "900", marginTop: 4, letterSpacing: -1 }}>Morning, {firstName}.</Text>
        <Text style={{ color: colors.muted, fontSize: 15, marginTop: 4, fontWeight: "500" }}>Here's what needs your attention before the crews roll.</Text>

        {/* KPI strip */}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.lg }}>
          <Kpi label="Crews confirmed" value={`${digest.data?.jobs.length ?? 0} of ${digest.data?.jobs.length ?? 0}`} sub="Last reply 6:42 AM" onPress={() => router.push("/(tabs)/calls")} />
          <Kpi label="Drafts to review" value={`${briefing.data?.drafts_pending ?? 0}`} sub={`Potential value $${Math.round(potentialValue).toLocaleString()}`} onPress={() => router.push("/(tabs)/inbox")} highlight />
          <Kpi label="Back charge risk" value={`${briefing.data?.back_charges_open ?? 0}`} sub="Response due today" onPress={() => router.push("/(tabs)/inbox")} />
          <Kpi label="Schedule changes" value={`${briefing.data?.schedule_changes_open ?? 0}`} sub="Waiting on GC" onPress={() => router.push("/(tabs)/inbox")} />
        </View>

        {/* Preview morning call */}
        <View style={{ marginTop: spacing.lg, borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md, backgroundColor: colors.surfaceInverse }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm }}>
            <Icon name="phone-outgoing" size={18} color={colors.brandPrimary} />
            <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>PREVIEW MORNING CALL</Text>
          </View>
          {briefing.isLoading ? (
            <ActivityIndicator color={colors.brandPrimary} />
          ) : (
            <Text testID="briefing-summary" style={{ color: colors.onSurfaceInverse, fontSize: 15, fontWeight: "500", lineHeight: 22 }}>
              {briefing.data?.summary}
            </Text>
          )}
        </View>

        {/* Needs your call */}
        <SectionRow title="Needs your call" count={digest.data?.action_required_count ?? 0} onSeeAll={() => router.push("/(tabs)/inbox")} />

        {digest.data?.change_orders?.slice(0, 2).map((co: any) => (
          <DraftCard
            key={co.id}
            type="CHANGE ORDER DRAFT"
            typeColor={colors.brandPrimary}
            reported={`Reported by ${co.reported_by || "field"}`}
            title={co.title || co.description}
            subtitle={`${co.job_name}${co.reported_by_phone ? " · " + co.reported_by_phone : ""}`}
            quote={co.description}
            money={co.ai_estimate ?? co.amount}
            leftLabels={co.labor_hours ? [{ k: "LABOR", v: `${co.labor_hours} hrs` }] : []}
            rightLabels={co.material_notes ? [{ k: "MATERIAL", v: co.material_notes }] : []}
            onOpen={() => router.push("/(tabs)/inbox")}
          />
        ))}
        {digest.data?.back_charges?.slice(0, 1).map((bc: any) => (
          <DraftCard
            key={bc.id}
            type="BACK CHARGE FLAG"
            typeColor={colors.error}
            reported={`Reported by ${bc.reported_by || "field"}`}
            title={bc.title || bc.description}
            subtitle={`${bc.job_name}${bc.reported_by_phone ? " · " + bc.reported_by_phone : ""}`}
            quote={bc.description}
            money={-bc.amount}
            onOpen={() => router.push("/(tabs)/inbox")}
          />
        ))}

        {/* Crews in motion */}
        <SectionRow title="Crews in motion" count={digest.data?.jobs.length ?? 0} onSeeAll={() => router.push("/(tabs)/jobs")} />
        {digest.data?.jobs?.map((j) => (
          <Pressable key={j.id} testID={`crew-card-${j.id}`} onPress={() => router.push(`/job/${j.id}`)}
            style={{ borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md, marginBottom: spacing.sm, flexDirection: "row", alignItems: "flex-start", gap: spacing.md, backgroundColor: colors.surface }}>
            <View style={{ width: 48, height: 48, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: colors.onSurfaceInverse, fontWeight: "900", fontSize: 13, letterSpacing: 1 }}>{j.code || j.name.slice(0, 3).toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.onSurface, fontSize: 17, fontWeight: "900" }}>{j.name}</Text>
              <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600" }}>{j.address}</Text>
              <View style={{ marginTop: spacing.xs, flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
                <MiniInfo k="ON SITE" v={`${j.crew} · ${j.crew_size}`} />
              </View>
              <View style={{ marginTop: 4 }}>
                <MiniInfo k="WORKING ON" v={j.working_on} />
              </View>
              {j.next_milestone ? <Text style={{ color: colors.brandPrimary, fontSize: 13, fontWeight: "800", marginTop: spacing.xs }}>{j.next_milestone}</Text> : null}
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function Kpi({ label, value, sub, onPress, highlight }: { label: string; value: string; sub: string; onPress?: () => void; highlight?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} style={{
      width: "48%", borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md,
      backgroundColor: highlight ? colors.brandTertiary : colors.surface,
    }}>
      <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: colors.onSurface, fontSize: 28, fontWeight: "900", marginTop: 2 }}>{value}</Text>
      <Text style={{ color: colors.muted, fontSize: 11, marginTop: 2, fontWeight: "600" }}>{sub}</Text>
    </Pressable>
  );
}

function SectionRow({ title, count, onSeeAll }: { title: string; count: number; onSeeAll: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: spacing.xl, marginBottom: spacing.sm }}>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: spacing.sm }}>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "900" }}>{title}</Text>
        <Text style={{ color: colors.muted, fontSize: 22, fontWeight: "900" }}>{count}</Text>
      </View>
      <Pressable onPress={onSeeAll} hitSlop={8}>
        <Text style={{ color: colors.brandPrimary, fontSize: 12, fontWeight: "900", letterSpacing: 1 }}>VIEW ALL →</Text>
      </Pressable>
    </View>
  );
}

function MiniInfo({ k, v }: { k: string; v: string }) {
  const { colors } = useTheme();
  return (
    <Text style={{ color: colors.onSurface, fontSize: 12, fontWeight: "600" }}>
      <Text style={{ color: colors.muted, fontWeight: "900", letterSpacing: 1 }}>{k} </Text>
      {v}
    </Text>
  );
}

function DraftCard({ type, typeColor, reported, title, subtitle, quote, money, leftLabels, rightLabels, onOpen }: {
  type: string; typeColor: string; reported: string; title: string; subtitle: string; quote?: string;
  money?: number | null | undefined; leftLabels?: { k: string; v: string }[]; rightLabels?: { k: string; v: string }[]; onOpen: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View testID={`draft-card-${title.slice(0, 6)}`} style={{ borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface, padding: spacing.md, marginBottom: spacing.md }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <View style={{ backgroundColor: typeColor, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={{ color: "#FFFFFF", fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>{type}</Text>
            </View>
            <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "700" }}>{reported}</Text>
          </View>
          <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: spacing.sm }} numberOfLines={2}>{title}</Text>
          <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600", marginTop: 2 }}>{subtitle}</Text>
          {quote ? <Text style={{ color: colors.onSurface, fontSize: 13, fontStyle: "italic", marginTop: spacing.sm, lineHeight: 18 }} numberOfLines={3}>"{quote}"</Text> : null}
        </View>
      </View>

      {(leftLabels?.length || rightLabels?.length || money != null) && (
        <View style={{ marginTop: spacing.sm, flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {money != null ? (
            <View>
              <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>AI ESTIMATE</Text>
              <Text style={{ color: money >= 0 ? colors.onSurface : colors.error, fontSize: 22, fontWeight: "900" }}>${Math.abs(money).toLocaleString()}</Text>
            </View>
          ) : null}
          {leftLabels?.map((l, i) => (
            <View key={i}>
              <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>{l.k}</Text>
              <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "800" }}>{l.v}</Text>
            </View>
          ))}
          {rightLabels?.map((l, i) => (
            <View key={i}>
              <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>{l.k}</Text>
              <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "800" }}>{l.v}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={{ width: 8, height: 8, backgroundColor: colors.warning }} />
          <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 1 }}>DRAFT ONLY — NOT SENT</Text>
        </View>
        <Pressable onPress={onOpen} hitSlop={8}>
          <Text style={{ color: colors.brandPrimary, fontSize: 12, fontWeight: "900", letterSpacing: 1 }}>REVIEW →</Text>
        </Pressable>
      </View>
    </View>
  );
}
