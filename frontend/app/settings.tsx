import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, TextInput, Switch, Platform, KeyboardAvoidingView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Button, Card, Pill } from "@/src/components/ui";
import { apiGet, apiPatch, apiPost } from "@/src/api";
import { useAuth } from "@/src/auth/auth-context";

type RecoveryPreview = {
  body: string; phone_number: string | null; sms_opt_in: boolean;
  money: { grand_total: number; unsigned_change_orders_count: number; disputed_back_charges_count: number };
};

export default function SettingsScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [phone, setPhone] = useState(user?.phone_number ?? "");
  const [optIn, setOptIn] = useState<boolean>((user as any)?.sms_opt_in ?? false);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const preview = useQuery({ queryKey: ["recovery-preview"], queryFn: () => apiGet<RecoveryPreview>("/recovery/preview") });

  useEffect(() => {
    if (preview.data) {
      setPhone(preview.data.phone_number ?? "");
      setOptIn(!!preview.data.sms_opt_in);
    }
  }, [preview.data]);

  async function save() {
    setSaving(true);
    setFlash(null);
    try {
      await apiPatch("/settings", { phone_number: phone, sms_opt_in: optIn });
      await qc.invalidateQueries({ queryKey: ["recovery-preview"] });
      setFlash("Saved.");
    } catch (e: any) {
      setFlash(e?.message?.includes("400") ? "Phone number looks off." : "Save failed.");
    } finally { setSaving(false); }
  }

  async function sendNow() {
    setSending(true);
    setFlash(null);
    try {
      const r = await apiPost<{ delivered_via: string; twilio_configured: boolean }>("/recovery/send", {});
      setFlash(r.twilio_configured
        ? `Text sent to ${phone}.`
        : `Preview logged (Twilio not configured — will send once TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER are set).`);
    } catch (e: any) {
      setFlash(e?.message?.includes("400") ? "Add a phone number first." : "Send failed.");
    } finally { setSending(false); }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="settings-back" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>WEEKLY RECAP</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>Settings</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}>
        <Card>
          <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>WEEKLY RECOVERY TEXT</Text>
          <Text style={{ color: colors.onSurface, fontSize: 15, marginTop: 4 }}>
            Every Monday at 8 AM, we'll text you the total dollars sitting in unsigned change orders and disputed back charges older than 7 days.
          </Text>
        </Card>

        <View style={{ height: spacing.lg }} />
        <Text style={{ color: colors.onSurface, fontSize: 12, fontWeight: "900", letterSpacing: 2, marginBottom: spacing.xs }}>PHONE NUMBER</Text>
        <TextInput
          testID="settings-phone-input"
          value={phone}
          onChangeText={setPhone}
          placeholder="+1 555 123 4567"
          keyboardType="phone-pad"
          placeholderTextColor={colors.muted}
          style={{
            minHeight: 56, borderWidth: 2, borderColor: colors.borderStrong,
            paddingHorizontal: spacing.md, fontSize: 18, color: colors.onSurface,
            backgroundColor: colors.surface,
          }}
        />

        <View style={{ height: spacing.md }} />
        <Pressable testID="settings-opt-in-row" onPress={() => setOptIn(v => !v)}
          style={{ minHeight: 56, borderWidth: 2, borderColor: colors.borderStrong, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "800", flex: 1 }}>Text me every Monday</Text>
          <Switch value={optIn} onValueChange={setOptIn} testID="settings-opt-in-switch"
            trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
            thumbColor={colors.surface}
          />
        </Pressable>

        <View style={{ height: spacing.md }} />
        <Button testID="settings-save-btn" label={saving ? "Saving…" : "Save"} onPress={save} loading={saving} />

        {flash && (
          <Text testID="settings-flash" style={{ color: colors.onSurface, marginTop: spacing.sm, fontWeight: "700" }}>{flash}</Text>
        )}

        <View style={{ height: spacing.xl }} />
        <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>PREVIEW</Text>
        <View style={{ height: spacing.xs }} />
        <Card style={{ backgroundColor: colors.surfaceInverse }}>
          {preview.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (
            <>
              <Text testID="preview-body" style={{ color: colors.onSurfaceInverse, fontSize: 15, lineHeight: 22, fontWeight: "500" }}>
                {preview.data?.body || "No data."}
              </Text>
              <View style={{ height: spacing.sm }} />
              <Pill label={`$${preview.data?.money.grand_total?.toLocaleString?.() ?? 0}`} tone="brand" />
            </>
          )}
        </Card>

        <View style={{ height: spacing.md }} />
        <Button testID="settings-send-btn" label="Send Test Text Now" onPress={sendNow} loading={sending} variant="secondary" />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
