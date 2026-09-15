import React, { useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Card, Pill, Button } from "@/src/components/ui";
import { apiGet, apiPatch } from "@/src/api";

type Assignment = { id: string; crew: string; job_id: string; job_name: string; date: string; notes: string };
type CrewGroup = { crew: string; assignments: Assignment[] };
type Dispatch = { date: string; crews: CrewGroup[]; total: number };
type Job = { id: string; name: string; gc: string; crew: string };

export default function DispatchScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const dispatch = useQuery({ queryKey: ["dispatch"], queryFn: () => apiGet<Dispatch>("/dispatch") });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => apiGet<Job[]>("/jobs") });
  const [editing, setEditing] = useState<Assignment | null>(null);
  const [saving, setSaving] = useState(false);

  const dayLabel = dispatch.data?.date
    ? new Date(dispatch.data.date).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })
    : "Tomorrow";

  const availableCrews = Array.from(new Set([
    ...(dispatch.data?.crews.map(c => c.crew) ?? []),
    "Crew A", "Crew B", "Crew C",
  ]));

  async function reassignTo(jobId: string) {
    if (!editing) return;
    setSaving(true);
    try {
      await apiPatch(`/dispatch/${editing.id}`, { job_id: jobId });
      await qc.invalidateQueries({ queryKey: ["dispatch"] });
      setEditing(null);
    } catch (e) { console.warn("reassign failed", e); }
    finally { setSaving(false); }
  }

  async function switchCrew(crew: string) {
    if (!editing) return;
    setSaving(true);
    try {
      await apiPatch(`/dispatch/${editing.id}`, { crew });
      await qc.invalidateQueries({ queryKey: ["dispatch"] });
      setEditing({ ...editing, crew });
    } catch (e) { console.warn("crew switch failed", e); }
    finally { setSaving(false); }
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="dispatch-back" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>TOMORROW · {dayLabel.toUpperCase()}</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>Dispatch Board</Text>
        <Text testID="dispatch-total" style={{ color: colors.onSurfaceInverse, opacity: 0.8, fontSize: 13, marginTop: 4 }}>
          {dispatch.data?.total ?? 0} assignment{(dispatch.data?.total ?? 0) === 1 ? "" : "s"} · Tap any card to reassign
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
                  <Pressable key={a.id} testID={`assignment-${a.id}`} onPress={() => setEditing(a)}>
                    <Card style={{ marginBottom: spacing.sm, borderLeftWidth: 6, borderLeftColor: colors.brandPrimary }}>
                      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>{timeLabel}</Text>
                          <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "900", marginTop: 2 }}>{a.job_name}</Text>
                          {a.notes ? <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.xs }}>{a.notes}</Text> : null}
                        </View>
                        <Icon name="pencil" size={20} color={colors.onSurface} />
                      </View>
                    </Card>
                  </Pressable>
                );
              })}
            </View>
          ))
        )}
      </ScrollView>

      {/* Reassign modal */}
      <Modal visible={!!editing} animationType="slide" transparent onRequestClose={() => setEditing(null)}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" }}>
          <View style={{ backgroundColor: colors.surface, borderTopWidth: 2, borderColor: colors.borderStrong, paddingBottom: insets.bottom + spacing.lg }}>
            <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 2, borderColor: colors.borderStrong, flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>REASSIGN</Text>
                <Text style={{ color: colors.onSurface, fontSize: 20, fontWeight: "900" }}>{editing?.crew} → ?</Text>
              </View>
              <Pressable testID="dispatch-modal-close" onPress={() => setEditing(null)} hitSlop={12}>
                <Icon name="close" size={24} color={colors.onSurface} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 460 }} contentContainerStyle={{ padding: spacing.lg }}>
              <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2, marginBottom: spacing.sm }}>SWITCH CREW</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.md }}>
                {availableCrews.map((c) => (
                  <Pressable
                    key={c}
                    testID={`crew-chip-${c.replace(/\s/g, "-").toLowerCase()}`}
                    onPress={() => switchCrew(c)}
                    disabled={saving}
                    style={{
                      height: 40, paddingHorizontal: spacing.md, justifyContent: "center",
                      backgroundColor: editing?.crew === c ? colors.brandPrimary : "transparent",
                      borderWidth: 2, borderColor: colors.borderStrong, flexShrink: 0,
                    }}
                  >
                    <Text style={{ color: editing?.crew === c ? colors.onBrandPrimary : colors.onSurface, fontWeight: "900", letterSpacing: 1, fontSize: 12, textTransform: "uppercase" }}>
                      {c}
                    </Text>
                  </Pressable>
                ))}
              </ScrollView>

              <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2, marginTop: spacing.md, marginBottom: spacing.sm }}>MOVE TO JOB</Text>
              {(jobs.data ?? []).map((j) => (
                <Pressable
                  key={j.id}
                  testID={`reassign-job-${j.id}`}
                  onPress={() => reassignTo(j.id)}
                  disabled={saving}
                  style={{
                    minHeight: 64, borderWidth: 2, borderColor: colors.borderStrong,
                    padding: spacing.md, marginBottom: spacing.sm,
                    backgroundColor: editing?.job_id === j.id ? colors.brandTertiary : colors.surface,
                    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: "900" }}>{j.name}</Text>
                    <Text style={{ color: colors.muted, fontSize: 12, marginTop: 2 }}>{j.gc}</Text>
                  </View>
                  {editing?.job_id === j.id ? (
                    <Icon name="check-bold" size={22} color={colors.brandPrimary} />
                  ) : (
                    <Icon name="chevron-right" size={22} color={colors.onSurface} />
                  )}
                </Pressable>
              ))}
              {saving && <ActivityIndicator color={colors.brandPrimary} />}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}
