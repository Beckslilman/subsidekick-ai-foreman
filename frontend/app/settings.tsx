import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, TextInput, Switch, Platform, KeyboardAvoidingView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Button, Card } from "@/src/components/ui";
import { apiGet, apiPatch, apiPost } from "@/src/api";
import { useAuth } from "@/src/auth/auth-context";

type RecoveryPreview = { body: string; phone_number: string | null; sms_opt_in: boolean; money: any };

export default function SettingsScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [phone, setPhone] = useState(user?.phone_number ?? "");
  const [optIn, setOptIn] = useState<boolean>((user as any)?.sms_opt_in ?? false);
  const [ghlToken, setGhlToken] = useState("");
  const [ghlLocation, setGhlLocation] = useState((user as any)?.ghl_location_id ?? "");
  const [twSid, setTwSid] = useState("");
  const [twToken, setTwToken] = useState("");
  const [twFrom, setTwFrom] = useState("+12295857126");
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const preview = useQuery({ queryKey: ["recovery-preview"], queryFn: () => apiGet<RecoveryPreview>("/recovery/preview") });
  const backendStatus = useQuery({ queryKey: ["backend-status"], queryFn: () => apiGet<any>("/") });

  useEffect(() => { if (preview.data) { setPhone(preview.data.phone_number ?? ""); setOptIn(!!preview.data.sms_opt_in); } }, [preview.data]);

  async function saveRecovery() {
    setSaving(true); setFlash(null);
    try {
      await apiPatch("/settings", { phone_number: phone, sms_opt_in: optIn });
      qc.invalidateQueries({ queryKey: ["recovery-preview"] }); qc.invalidateQueries({ queryKey: ["auth-me"] });
      setFlash("Saved.");
    } catch (e: any) { setFlash(e?.message?.includes("400") ? "Phone number looks off." : "Save failed."); }
    finally { setSaving(false); }
  }

  async function saveIntegrations() {
    setSaving(true); setFlash(null);
    try {
      await apiPatch("/settings", {
        ghl_access_token: ghlToken || undefined,
        ghl_location_id: ghlLocation || undefined,
        twilio_account_sid: twSid || undefined,
        twilio_auth_token: twToken || undefined,
        twilio_from_number: twFrom || undefined,
      });
      setFlash("Integration settings saved. Ask your engineer to move Twilio/GHL keys into backend env for live sends.");
      qc.invalidateQueries({ queryKey: ["backend-status"] });
    } catch (e) { setFlash("Save failed."); }
    finally { setSaving(false); }
  }

  async function sendNow() {
    setSending(true); setFlash(null);
    try {
      const r = await apiPost<{ twilio_configured: boolean }>("/recovery/send", {});
      setFlash(r.twilio_configured ? `Text sent to ${phone}.` : `Preview logged to outbox (add Twilio keys to send live).`);
    } catch (e: any) { setFlash(e?.message?.includes("400") ? "Add a phone number first." : "Send failed."); }
    finally { setSending(false); }
  }

  const webhookUrl = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/webhooks/ghl/voice-ai`;
  const smsWebhook = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/webhooks/twilio/sms`;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="settings-back" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>OFFICE ADMIN</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>Settings</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}>
        {/* Setup / Status */}
        <Card style={{ backgroundColor: colors.surfaceInverse, borderColor: colors.brandPrimary }}>
          <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>INTEGRATIONS STATUS</Text>
          <StatusRow label="Twilio SMS/Voice" ok={!!backendStatus.data?.twilio_configured} hint="AI hotline + weekly recovery texts" />
          <StatusRow label="GHL Voice AI" ok={!!backendStatus.data?.ghl_configured} hint="Voice AI on inbound/outbound calls" />
        </Card>

        {/* Weekly recovery */}
        <SectionLabel>Weekly recovery text</SectionLabel>
        <Card>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm }}>
            Every Monday 8 AM, we'll text you the dollars sitting in unsigned change orders and disputed back charges older than 7 days.
          </Text>
          <Field label="Phone Number">
            <TextInput testID="settings-phone-input" value={phone} onChangeText={setPhone} placeholder="+1 555 123 4567" keyboardType="phone-pad" placeholderTextColor={colors.muted}
              style={inputStyle(colors)} />
          </Field>
          <View style={{ height: spacing.sm }} />
          <Pressable testID="settings-opt-in-row" onPress={() => setOptIn(v => !v)}
            style={{ minHeight: 48, borderWidth: 2, borderColor: colors.borderStrong, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "800", flex: 1 }}>Text me every Monday</Text>
            <Switch value={optIn} onValueChange={setOptIn} testID="settings-opt-in-switch"
              trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }} thumbColor={colors.surface} />
          </Pressable>
          <View style={{ height: spacing.sm }} />
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <View style={{ flex: 1 }}><Button testID="settings-save-btn" label="Save" onPress={saveRecovery} loading={saving} /></View>
            <View style={{ flex: 1 }}><Button testID="settings-send-btn" label="Test Text" onPress={sendNow} loading={sending} variant="secondary" /></View>
          </View>
          {flash && <Text testID="settings-flash" style={{ color: colors.onSurface, marginTop: spacing.sm, fontWeight: "700" }}>{flash}</Text>}
        </Card>

        {/* Twilio setup */}
        <SectionLabel>Twilio Voice + SMS setup</SectionLabel>
        <Card>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>1.</Text> Sign in at twilio.com → Console → Account SID + Auth Token.{"\n"}
            <Text style={{ fontWeight: "900" }}>2.</Text> Buy or claim a voice-enabled number. Your number: <Text style={{ fontWeight: "900" }}>+1 (229) 585-7126</Text>.{"\n"}
            <Text style={{ fontWeight: "900" }}>3.</Text> In your Twilio number's messaging config, set inbound SMS webhook to:
          </Text>
          <Mono>{smsWebhook}</Mono>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>4.</Text> For voice, forward the number to GHL Voice AI, or point it at your GHL SIP.
          </Text>
          <View style={{ height: spacing.sm }} />
          <Field label="Twilio Account SID"><TextInput value={twSid} onChangeText={setTwSid} placeholder="AC..." placeholderTextColor={colors.muted} style={inputStyle(colors)} testID="tw-sid" /></Field>
          <View style={{ height: 8 }} />
          <Field label="Twilio Auth Token"><TextInput value={twToken} onChangeText={setTwToken} placeholder="********" placeholderTextColor={colors.muted} secureTextEntry style={inputStyle(colors)} testID="tw-token" /></Field>
          <View style={{ height: 8 }} />
          <Field label="Twilio From Number"><TextInput value={twFrom} onChangeText={setTwFrom} placeholder="+12295857126" placeholderTextColor={colors.muted} style={inputStyle(colors)} testID="tw-from" /></Field>
        </Card>

        {/* GHL setup */}
        <SectionLabel>GHL Voice AI setup</SectionLabel>
        <Card>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>1.</Text> In GHL, Settings → Business Profile → Private Integration Token (or install as a Marketplace app).{"\n"}
            <Text style={{ fontWeight: "900" }}>2.</Text> Copy the token + your Location ID (Sub-account settings).{"\n"}
            <Text style={{ fontWeight: "900" }}>3.</Text> Set Voice AI's post-call webhook to:
          </Text>
          <Mono>{webhookUrl}</Mono>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>4.</Text> Configure the Voice AI agent to extract change_orders, back_charges, and schedule_changes and include them in the webhook payload.
          </Text>
          <View style={{ height: spacing.sm }} />
          <Field label="GHL Access Token (write-only)"><TextInput value={ghlToken} onChangeText={setGhlToken} placeholder="Paste PIT or OAuth token" placeholderTextColor={colors.muted} secureTextEntry style={inputStyle(colors)} testID="ghl-token" /></Field>
          <View style={{ height: 8 }} />
          <Field label="GHL Location ID"><TextInput value={ghlLocation} onChangeText={setGhlLocation} placeholder="Loc-abc123" placeholderTextColor={colors.muted} style={inputStyle(colors)} testID="ghl-location" /></Field>
        </Card>

        <View style={{ height: spacing.md }} />
        <Button testID="save-integrations-btn" label="Save Integration Keys" onPress={saveIntegrations} loading={saving} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function SectionLabel({ children }: { children: string }) {
  const { colors } = useTheme();
  return <Text style={{ color: colors.onSurface, fontSize: 14, fontWeight: "900", letterSpacing: 2, textTransform: "uppercase", marginTop: spacing.xl, marginBottom: spacing.sm }}>{children}</Text>;
}
function StatusRow({ label, ok, hint }: { label: string; ok: boolean; hint: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ marginTop: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
      <View style={{ width: 12, height: 12, backgroundColor: ok ? colors.success : colors.warning }} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.onSurfaceInverse, fontWeight: "900", fontSize: 14 }}>{label}</Text>
        <Text style={{ color: colors.onSurfaceInverse, opacity: 0.7, fontSize: 12 }}>{ok ? "Connected · " + hint : "Not connected · " + hint}</Text>
      </View>
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
function Mono({ children }: { children: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.sm, backgroundColor: colors.surfaceTertiary }}>
      <Text selectable style={{ color: colors.onSurface, fontSize: 11, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" }}>{children}</Text>
    </View>
  );
}
function inputStyle(colors: any) {
  return {
    minHeight: 48, borderWidth: 2, borderColor: colors.borderStrong,
    paddingHorizontal: spacing.md, fontSize: 15, color: colors.onSurface, backgroundColor: colors.surface,
  } as any;
}
