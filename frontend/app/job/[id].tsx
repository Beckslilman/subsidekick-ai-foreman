import React from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Pill, Card } from "@/src/components/ui";
import { apiGet } from "@/src/api";

export default function JobDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();

  const job = useQuery({ queryKey: ["job", id], queryFn: () => apiGet<any>(`/jobs/${id}`), enabled: !!id });
  const cos = useQuery({ queryKey: ["change-orders"], queryFn: () => apiGet<any[]>("/change-orders") });
  const bcs = useQuery({ queryKey: ["back-charges"], queryFn: () => apiGet<any[]>("/back-charges") });
  const inspections = useQuery({ queryKey: ["inspections"], queryFn: () => apiGet<any[]>("/inspections") });

  if (job.isLoading || !job.data) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface }}><ActivityIndicator color={colors.brandPrimary} /></View>;

  const j = job.data;
  const jobCos = (cos.data ?? []).filter((c) => c.job_id === id);
  const jobBcs = (bcs.data ?? []).filter((b) => b.job_id === id);
  const jobIns = (inspections.data ?? []).filter((i) => i.job_id === id);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>{j.gc}</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>{j.name}</Text>
        <Text style={{ color: colors.onSurfaceInverse, opacity: 0.7, fontSize: 13, marginTop: 4 }}>{j.address}</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}>
        <Card>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <View>
              <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "800", letterSpacing: 1 }}>PROGRESS</Text>
              <Text style={{ color: colors.onSurface, fontSize: 32, fontWeight: "900" }}>{j.progress}%</Text>
            </View>
            <View>
              <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "800", letterSpacing: 1 }}>CREW</Text>
              <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900" }}>{j.crew || "—"}</Text>
            </View>
            <Pill label={j.status} tone={j.status === "active" ? "success" : "neutral"} />
          </View>
          <View style={{ height: 8, backgroundColor: colors.surfaceTertiary, marginTop: spacing.md, borderWidth: 1, borderColor: colors.borderStrong }}>
            <View style={{ width: `${j.progress}%`, height: "100%", backgroundColor: colors.brandPrimary }} />
          </View>
        </Card>

        <Section title={`Change Orders (${jobCos.length})`} icon="file-document-edit">
          {jobCos.length === 0 ? <EmptyRow label="No change orders." /> : jobCos.map((co: any) => (
            <Row key={co.id} title={co.description} right={<Pill label={co.status} tone="warning" />} sub={`$${(co.amount ?? 0).toFixed(0)}`} />
          ))}
        </Section>

        <Section title={`Back Charges (${jobBcs.length})`} icon="alert-octagon">
          {jobBcs.length === 0 ? <EmptyRow label="No back charges." /> : jobBcs.map((bc: any) => (
            <Row key={bc.id} title={bc.description} right={<Pill label={bc.status} tone="error" />} sub={`-$${bc.amount.toFixed(0)}`} />
          ))}
        </Section>

        <Section title={`Inspections (${jobIns.length})`} icon="clipboard-check">
          {jobIns.length === 0 ? <EmptyRow label="No inspections." /> : jobIns.map((ins: any) => (
            <Row key={ins.id} title={`${ins.inspection_type} — ${ins.result.toUpperCase()}`} right={
              <Pill label={ins.result} tone={ins.result === "pass" ? "success" : ins.result === "fail" ? "error" : "neutral"} />
            } sub={ins.notes} />
          ))}
        </Section>
      </ScrollView>
    </View>
  );
}

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ marginTop: spacing.lg }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: spacing.sm }}>
        <Icon name={icon as any} size={18} color={colors.onSurface} />
        <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "900", letterSpacing: 1, textTransform: "uppercase" }}>{title}</Text>
      </View>
      {children}
    </View>
  );
}
function Row({ title, right, sub }: { title: string; right?: React.ReactNode; sub?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ borderTopWidth: 2, borderColor: colors.borderStrong, paddingVertical: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 64 }}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "700" }} numberOfLines={2}>{title}</Text>
        {sub ? <Text style={{ color: colors.muted, fontSize: 12, marginTop: 2, fontWeight: "600" }}>{sub}</Text> : null}
      </View>
      {right}
    </View>
  );
}
function EmptyRow({ label }: { label: string }) {
  const { colors } = useTheme();
  return <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.md }}>{label}</Text>;
}
