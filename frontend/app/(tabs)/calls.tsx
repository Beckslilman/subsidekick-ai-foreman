import React, { useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, Modal, TextInput, Platform, KeyboardAvoidingView, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Button, Card, Pill } from "@/src/components/ui";
import { apiGet, apiPost, apiPatch, apiDelete } from "@/src/api";

type TeamMember = { id: string; name: string; role: string; phone_number: string; timezone: string; briefing_hour: number; briefing_minute: number; briefing_enabled: boolean };
type CallLog = { id: string; direction: "inbound" | "outbound"; channel: "voice" | "sms"; from_number: string; to_number: string; team_member_name?: string; duration_sec: number; summary?: string; started_at: string; extracted_drafts?: string[] };

export default function CallsScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: () => apiGet<TeamMember[]>("/team") });
  const calls = useQuery({ queryKey: ["calls"], queryFn: () => apiGet<CallLog[]>("/calls") });
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState(""); const [phone, setPhone] = useState("");
  const [hour, setHour] = useState("6"); const [minute, setMinute] = useState("30");
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const HOTLINE = "+1 (229) 585-7126";

  async function saveMember() {
    if (!name.trim() || !phone.trim()) return;
    setSaving(true);
    try {
      await apiPost("/team", { name, phone_number: phone, briefing_hour: parseInt(hour, 10) || 6, briefing_minute: parseInt(minute, 10) || 30 });
      setName(""); setPhone(""); setHour("6"); setMinute("30"); setAddOpen(false);
      qc.invalidateQueries({ queryKey: ["team"] });
    } catch (e: any) {
      setFlash(e?.message?.includes("400") ? "Phone number looks off." : "Save failed.");
    } finally { setSaving(false); }
  }

  async function trigger(id: string) {
    setTriggering(id); setFlash(null);
    try {
      const r = await apiPost<{ delivered_via: string; twilio_configured: boolean }>(`/team/${id}/trigger-briefing`, {});
      if (r.delivered_via === "ghl") {
        setFlash("Morning briefing SMS sent via GHL.");
      } else if (r.delivered_via === "twilio") {
        setFlash("Morning briefing SMS sent via Twilio.");
      } else {
        setFlash("Briefing logged to outbox (set GHL or Twilio Deployment Secrets to send live).");
      }
      qc.invalidateQueries({ queryKey: ["calls"] });
    } catch (e) { setFlash("Trigger failed."); }
    finally { setTriggering(null); }
  }

  async function removeMember(id: string) {
    try { await apiDelete(`/team/${id}`); qc.invalidateQueries({ queryKey: ["team"] }); } catch {}
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>CALL CENTER</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Voice & SMS</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={team.isFetching || calls.isFetching} onRefresh={() => { qc.invalidateQueries({ queryKey: ["team"] }); qc.invalidateQueries({ queryKey: ["calls"] }); }} tintColor={colors.brandPrimary} />}>

        {/* Hotline card */}
        <Card style={{ backgroundColor: colors.surfaceInverse, borderColor: colors.brandPrimary, marginBottom: spacing.md }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm }}>
            <Icon name="phone" size={22} color={colors.brandPrimary} />
            <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>24/7 AI HOTLINE</Text>
          </View>
          <Text testID="hotline-number" style={{ color: colors.onSurfaceInverse, fontSize: 32, fontWeight: "900", letterSpacing: 1 }}>{HOTLINE}</Text>
          <Text style={{ color: colors.onSurfaceInverse, opacity: 0.85, fontSize: 13, marginTop: 4 }}>
            Field supers call or text this number. AI captures change orders, back charges, schedule changes, and daily check-ins as drafts.
          </Text>
        </Card>

        {/* Team */}
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm, marginBottom: spacing.sm }}>
          <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "900", letterSpacing: 2, textTransform: "uppercase" }}>Field team ({team.data?.length ?? 0})</Text>
          <Pressable testID="add-team-btn" onPress={() => setAddOpen(true)} hitSlop={8}>
            <Text style={{ color: colors.brandPrimary, fontWeight: "900", letterSpacing: 1, fontSize: 12 }}>+ ADD SUPER</Text>
          </Pressable>
        </View>
        {team.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (team.data ?? []).map((tm) => (
          <View key={tm.id} testID={`team-row-${tm.id}`}
            style={{ borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md, marginBottom: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.md }}>
            <View style={{ width: 44, height: 44, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
              <Text style={{ color: colors.brandPrimary, fontWeight: "900", fontSize: 14 }}>{tm.name.split(" ").map(p => p[0]).slice(0, 2).join("")}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: "900" }}>{tm.name}</Text>
              <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600" }}>{tm.phone_number} · {tm.role}</Text>
              <Text style={{ color: colors.muted, fontSize: 11, marginTop: 2 }}>Auto-briefing {String(tm.briefing_hour).padStart(2, "0")}:{String(tm.briefing_minute).padStart(2, "0")}</Text>
            </View>
            <Pressable testID={`trigger-${tm.id}`} onPress={() => trigger(tm.id)} disabled={triggering === tm.id}
              style={{ paddingHorizontal: spacing.sm, minHeight: 44, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
              {triggering === tm.id ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : (
                <Text style={{ color: colors.onBrandPrimary, fontWeight: "900", letterSpacing: 1, fontSize: 11 }}>BRIEF NOW</Text>
              )}
            </Pressable>
            <Pressable testID={`team-remove-${tm.id}`} onPress={() => removeMember(tm.id)} hitSlop={8}>
              <Icon name="trash-can-outline" size={20} color={colors.muted} />
            </Pressable>
          </View>
        ))}
        {flash && <Text testID="calls-flash" style={{ color: colors.onSurface, marginTop: spacing.xs, fontWeight: "700" }}>{flash}</Text>}

        {/* Call log */}
        <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "900", letterSpacing: 2, textTransform: "uppercase", marginTop: spacing.xl, marginBottom: spacing.sm }}>Recent calls</Text>
        {calls.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> :
          (calls.data ?? []).length === 0 ? (
            <Text style={{ color: colors.muted, fontWeight: "700" }}>No calls yet.</Text>
          ) : (calls.data ?? []).map((c) => (
            <View key={c.id} testID={`call-row-${c.id}`}
              style={{ borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md, marginBottom: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: 4 }}>
                <Icon name={c.direction === "inbound" ? "phone-incoming" : "phone-outgoing"} size={16} color={c.direction === "inbound" ? colors.success : colors.brandPrimary} />
                <Text style={{ color: colors.muted, fontSize: 10, fontWeight: "900", letterSpacing: 2 }}>
                  {c.direction === "inbound" ? "INBOUND" : "OUTBOUND"} · {c.channel.toUpperCase()} · {new Date(c.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                </Text>
              </View>
              <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "800" }}>{c.team_member_name || c.from_number}</Text>
              {c.summary ? <Text style={{ color: colors.onSurface, fontSize: 13, marginTop: 4 }} numberOfLines={2}>{c.summary}</Text> : null}
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs }}>
                {c.duration_sec > 0 ? <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "700" }}>{Math.floor(c.duration_sec / 60)}:{String(c.duration_sec % 60).padStart(2, "0")}</Text> : null}
                {(c.extracted_drafts?.length ?? 0) > 0 ? <Pill label={`${c.extracted_drafts?.length} DRAFT${c.extracted_drafts && c.extracted_drafts.length > 1 ? "S" : ""}`} tone="warning" /> : null}
              </View>
            </View>
          ))
        }
      </ScrollView>

      {/* Add Super modal */}
      <Modal visible={addOpen} animationType="slide" transparent onRequestClose={() => setAddOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" }}>
          <View style={{ backgroundColor: colors.surface, borderTopWidth: 2, borderColor: colors.borderStrong, paddingBottom: insets.bottom + spacing.lg }}>
            <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 2, borderColor: colors.borderStrong, flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ color: colors.onSurface, fontSize: 20, fontWeight: "900" }}>Add super</Text>
              <Pressable testID="add-close" onPress={() => setAddOpen(false)} hitSlop={12}>
                <Icon name="close" size={24} color={colors.onSurface} />
              </Pressable>
            </View>
            <View style={{ padding: spacing.lg, gap: spacing.md }}>
              <Field label="Name">
                <TextInput testID="add-name" value={name} onChangeText={setName} placeholder="Rick Martinez" placeholderTextColor={colors.muted}
                  style={inputStyle(colors)} />
              </Field>
              <Field label="Phone">
                <TextInput testID="add-phone" value={phone} onChangeText={setPhone} placeholder="+1 555 123 4567" keyboardType="phone-pad" placeholderTextColor={colors.muted}
                  style={inputStyle(colors)} />
              </Field>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Field label="Brief Hour (24h)">
                    <TextInput testID="add-hour" value={hour} onChangeText={setHour} keyboardType="numeric" style={inputStyle(colors)} />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Minute">
                    <TextInput testID="add-min" value={minute} onChangeText={setMinute} keyboardType="numeric" style={inputStyle(colors)} />
                  </Field>
                </View>
              </View>
              <Button testID="add-save" label="Save Super" onPress={saveMember} loading={saving} />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View>
      <Text style={{ color: colors.onSurface, fontSize: 11, fontWeight: "900", letterSpacing: 2, marginBottom: 4 }}>{label.toUpperCase()}</Text>
      {children}
    </View>
  );
}
function inputStyle(colors: any) {
  return {
    minHeight: 56, borderWidth: 2, borderColor: colors.borderStrong,
    paddingHorizontal: spacing.md, fontSize: 16, color: colors.onSurface, backgroundColor: colors.surface,
  } as any;
}
