import React, { useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import Icon from "@react-native-vector-icons/material-design-icons";
import { useTheme, spacing } from "@/src/theme";
import { Button, Card, Pill } from "@/src/components/ui";
import { apiPost } from "@/src/api";

type StartResp = { checkin_id: string; total_jobs: number; current_index: number; current_job: any };
type AnswerResp = { checkin_id: string; answered_count: number; total_jobs: number; current_job?: any; done: boolean; summary?: string };

export default function CheckinScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const [session, setSession] = useState<StartResp | null>(null);
  const [currentJob, setCurrentJob] = useState<any | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [completed, setCompleted] = useState("");
  const [issues, setIssues] = useState("");
  const [busy, setBusy] = useState(false);
  const [doneSummary, setDoneSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<StartResp>("/checkin/start");
      setSession(r);
      setCurrentJob(r.current_job);
      setProgress({ done: 0, total: r.total_jobs });
    } catch (e: any) {
      setError("Couldn't start check-in.");
    } finally { setBusy(false); }
  }

  async function submitAnswer() {
    if (!session || !currentJob || busy) return;
    setBusy(true);
    try {
      const r = await apiPost<AnswerResp>("/checkin/answer", {
        checkin_id: session.checkin_id,
        job_id: currentJob.id,
        completed, issues,
      });
      setCompleted(""); setIssues("");
      setProgress({ done: r.answered_count, total: r.total_jobs });
      if (r.done) {
        setDoneSummary(r.summary || "Day wrapped up.");
        setCurrentJob(null);
        qc.invalidateQueries();
      } else {
        setCurrentJob(r.current_job);
      }
    } finally { setBusy(false); }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Header */}
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Pressable testID="checkin-back" onPress={() => router.back()} hitSlop={16} style={{ marginBottom: spacing.xs }}>
          <Icon name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>WRAP UP</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "900" }}>End of Day</Text>
        {session && !doneSummary && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm }}>
            <View style={{ flex: 1, height: 6, backgroundColor: "#1F2937", borderWidth: 1, borderColor: colors.brandPrimary }}>
              <View style={{
                width: `${(progress.done / Math.max(1, progress.total)) * 100}%`,
                height: "100%", backgroundColor: colors.brandPrimary,
              }} />
            </View>
            <Text style={{ color: colors.onSurfaceInverse, fontWeight: "900", fontSize: 12 }}>
              {progress.done}/{progress.total}
            </Text>
          </View>
        )}
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xxxl }}>
        {error && <Text style={{ color: colors.error, marginBottom: spacing.md, fontWeight: "700" }}>{error}</Text>}

        {!session && !doneSummary && (
          <>
            <Card>
              <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "800", lineHeight: 24 }}>
                Walk through today's jobs, one at a time. Tell me what got done and anything that went sideways.
              </Text>
              <View style={{ height: spacing.md }} />
              <Text style={{ color: colors.muted, fontSize: 14, fontWeight: "600" }}>
                Failed inspection mentions auto-log a draft for the office.
              </Text>
            </Card>
            <View style={{ height: spacing.lg }} />
            <Button testID="checkin-start-btn" label="Start Check-In" onPress={start} loading={busy} />
          </>
        )}

        {session && currentJob && !doneSummary && (
          <>
            <Card>
              <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>JOB {progress.done + 1}</Text>
              <Text testID="checkin-job-name" style={{ color: colors.onSurface, fontSize: 24, fontWeight: "900", marginTop: 4 }}>
                {currentJob.name}
              </Text>
              <Text style={{ color: colors.muted, fontSize: 13, fontWeight: "700", marginTop: 2 }}>
                {currentJob.gc} · {currentJob.crew || "Unassigned"}
              </Text>
              <View style={{ marginTop: spacing.sm }}>
                <Pill label={currentJob.status} tone={currentJob.status === "active" ? "success" : "neutral"} />
              </View>
            </Card>

            <View style={{ height: spacing.md }} />
            <Field label="What got done?">
              <TextInput
                testID="checkin-completed-input"
                value={completed}
                onChangeText={setCompleted}
                placeholder="e.g. finished east wall base coat"
                placeholderTextColor={colors.muted}
                multiline
                style={{
                  minHeight: 88, borderWidth: 2, borderColor: colors.borderStrong,
                  padding: spacing.md, fontSize: 16, color: colors.onSurface,
                  textAlignVertical: "top", backgroundColor: colors.surface,
                }}
              />
            </Field>

            <View style={{ height: spacing.md }} />
            <Field label="Any issues?">
              <TextInput
                testID="checkin-issues-input"
                value={issues}
                onChangeText={setIssues}
                placeholder="e.g. failed framing inspection on 2nd floor"
                placeholderTextColor={colors.muted}
                multiline
                style={{
                  minHeight: 88, borderWidth: 2, borderColor: colors.borderStrong,
                  padding: spacing.md, fontSize: 16, color: colors.onSurface,
                  textAlignVertical: "top", backgroundColor: colors.surface,
                }}
              />
            </Field>

            <View style={{ height: spacing.lg }} />
            <Button testID="checkin-next-btn" label={progress.done + 1 === progress.total ? "Finish Day" : "Next Job"} onPress={submitAnswer} loading={busy} />
          </>
        )}

        {doneSummary && (
          <View>
            <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
              <View style={{ width: 88, height: 88, backgroundColor: colors.success, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
                <Icon name="check-bold" size={44} color={colors.onSuccess} />
              </View>
              <Text style={{ marginTop: spacing.md, color: colors.onSurface, fontSize: 22, fontWeight: "900" }}>DAY WRAPPED</Text>
            </View>
            <Card style={{ backgroundColor: colors.surfaceInverse }}>
              <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>OFFICE SUMMARY</Text>
              <Text testID="checkin-summary" style={{ color: colors.onSurfaceInverse, fontSize: 16, fontWeight: "500", lineHeight: 24, marginTop: spacing.sm }}>
                {doneSummary}
              </Text>
            </Card>
            <View style={{ height: spacing.lg }} />
            <Button label="Back to Briefing" onPress={() => router.replace("/(tabs)")} />
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View>
      <Text style={{ color: colors.onSurface, fontSize: 12, fontWeight: "900", letterSpacing: 2, marginBottom: spacing.xs }}>{label.toUpperCase()}</Text>
      {children}
    </View>
  );
}
