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
  const [ghlLocation, setGhlLocation] = useState((user as any)?.ghl_location_id ?? "");
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
        ghl_location_id: ghlLocation || undefined,
        twilio_from_number: twFrom || undefined,
      });
      setFlash("Saved location/from-number. Live Twilio/GHL still use Deployment Secrets on the server — SID, Auth Token, and GHL PIT are not stored from this form.");
      qc.invalidateQueries({ queryKey: ["backend-status"] });
    } catch (e) { setFlash("Save failed."); }
    finally { setSaving(false); }
  }

  async function sendNow() {
    setSending(true); setFlash(null);
    try {
      const r = await apiPost<{ twilio_configured: boolean; delivered_via?: string; sms_provider?: string | null }>("/recovery/send", {});
      const sent = r.delivered_via && r.delivered_via !== "outbox";
      setFlash(sent
        ? `Text sent to ${phone} via ${r.delivered_via}.`
        : "Preview logged to outbox (set GHL_ACCESS_TOKEN + GHL_LOCATION_ID, or TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN, to send live).");
    } catch (e: any) { setFlash(e?.message?.includes("400") ? "Add a phone number first." : "Send failed."); }
    finally { setSending(false); }
  }

  const webhookUrl = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/webhooks/ghl/voice-ai`;
  const smsWebhook = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/webhooks/twilio/sms`;
  const ghlInboundSms = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/webhooks/ghl/inbound-sms`;
  const smsProvider = backendStatus.data?.sms_provider as string | null | undefined;
  const smsHint = smsProvider === "ghl"
    ? "GHL Conversations (LeadConnector numbers — no Twilio SID needed)"
    : smsProvider === "twilio"
      ? "Twilio Account SID + Auth Token"
      : "Needs GHL_ACCESS_TOKEN + GHL_LOCATION_ID, or TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN";

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
          <StatusRow label="Outbound SMS" ok={!!smsProvider} hint={smsHint} />
          <StatusRow label="Twilio SMS/Voice" ok={!!backendStatus.data?.twilio_configured} hint="Optional — used when Account SID + Auth Token are set" />
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

        {/* Deployment secrets — env is source of truth; this form does not store SID/token */}
        <SectionLabel>Deployment Secrets (required for live SMS/voice)</SectionLabel>
        <Card style={{ borderColor: colors.brandPrimary }}>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm, fontWeight: "800" }}>
            Live Twilio and GHL credentials are server env vars. They are not saved from this screen and typing them here cannot enable sending.
          </Text>
          <Text style={{ color: colors.onSurface, fontSize: 13, lineHeight: 20 }}>
            Set these on the backend / host:{'\n'}
            LeadConnector SMS (no Twilio console): <Text style={{ fontWeight: "900" }}>GHL_ACCESS_TOKEN</Text>, <Text style={{ fontWeight: "900" }}>GHL_LOCATION_ID</Text>, optional <Text style={{ fontWeight: "900" }}>TWILIO_FROM</Text> / <Text style={{ fontWeight: "900" }}>TWILIO_FROM_NUMBER</Text> (defaults to +12295857126).{'\n'}
            Optional native Twilio: <Text style={{ fontWeight: "900" }}>TWILIO_ACCOUNT_SID</Text>, <Text style={{ fontWeight: "900" }}>TWILIO_AUTH_TOKEN</Text>{'\n'}
            Voice AI signatures: <Text style={{ fontWeight: "900" }}>GHL_PUBLIC_KEY</Text>{'\n'}
            Optional preview bypasses (never in production): <Text style={{ fontWeight: "900" }}>TWILIO_SKIP_SIGNATURE_CHECK=1</Text>, <Text style={{ fontWeight: "900" }}>ALLOW_DEV_LOGIN=1</Text>
          </Text>
        </Card>

        {/* Twilio setup */}
        <SectionLabel>Twilio Voice + SMS setup</SectionLabel>
        <Card>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>1.</Text> Sign in at twilio.com → Console → copy Account SID + Auth Token into Deployment Secrets.{'\n'}
            <Text style={{ fontWeight: "900" }}>2.</Text> Buy or claim a voice-enabled number. Your number: <Text style={{ fontWeight: "900" }}>+1 (229) 585-7126</Text>.{'\n'}
            <Text style={{ fontWeight: "900" }}>3.</Text> In your Twilio number's messaging config, set inbound SMS webhook to:
          </Text>
          <Mono>{smsWebhook}</Mono>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>4.</Text> For voice, forward the number to GHL Voice AI, or point it at your GHL SIP.
          </Text>
          <View style={{ height: spacing.sm }} />
          <Field label="Twilio From Number (display / office note — live sends still use TWILIO_FROM_NUMBER env)">
            <TextInput value={twFrom} onChangeText={setTwFrom} placeholder="+12295857126" placeholderTextColor={colors.muted} style={inputStyle(colors)} testID="tw-from" />
          </Field>
        </Card>

        {/* GHL setup */}
        <SectionLabel>GHL Voice AI setup</SectionLabel>
        <Card>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginBottom: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>1.</Text> In GHL, Settings → Business Profile → Private Integration Token (or install as a Marketplace app). Put the token in <Text style={{ fontWeight: "900" }}>GHL_ACCESS_TOKEN</Text> (Deployment Secret).{'\n'}
            <Text style={{ fontWeight: "900" }}>2.</Text> Copy your Location ID (Sub-account settings). You can store the Location ID here; the access token cannot.{'\n'}
            <Text style={{ fontWeight: "900" }}>3.</Text> Set Voice AI's post-call webhook to:
          </Text>
          <Mono>{webhookUrl}</Mono>
          <Text style={{ color: colors.onSurface, fontSize: 14, marginTop: spacing.sm }}>
            <Text style={{ fontWeight: "900" }}>4.</Text> Configure the Voice AI agent to extract change_orders, back_charges, and schedule_changes and include them in the webhook payload. Set <Text style={{ fontWeight: "900" }}>GHL_PUBLIC_KEY</Text> so unsigned webhooks are rejected.{'\n'}
            <Text style={{ fontWeight: "900" }}>5.</Text> Optional — for texts into the LC number, add a GHL <Text style={{ fontWeight: "900" }}>InboundMessage</Text> webhook:
          </Text>
          <Mono>{ghlInboundSms}</Mono>
          <View style={{ height: spacing.sm }} />
          <Field label="GHL Location ID (not the access token)">
            <TextInput value={ghlLocation} onChangeText={setGhlLocation} placeholder="Loc-abc123" placeholderTextColor={colors.muted} style={inputStyle(colors)} testID="ghl-location" />
          </Field>
        </Card>

        <View style={{ height: spacing.md }} />
        <Button testID="save-integrations-btn" label="Save Integration Settings" onPress={saveIntegrations} loading={saving} />
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
