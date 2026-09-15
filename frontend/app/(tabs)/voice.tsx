import React, { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, Platform, Image } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/material-design-icons";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState, createAudioPlayer } from "expo-audio";
import * as ImagePicker from "expo-image-picker";
import { useTheme, spacing } from "@/src/theme";
import { apiGet, apiPost, uploadAudio, uploadPhoto, API_BASE } from "@/src/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getToken } from "@/src/auth/token-store";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string; audio_key?: string | null; created_at: string };

export default function VoiceScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recState = useAudioRecorderState(recorder);
  const [busy, setBusy] = useState(false);
  const [pendingPhoto, setPendingPhoto] = useState<{ url: string; localUri: string } | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const qc = useQueryClient();
  const scrollRef = useRef<ScrollView>(null);
  const playerRef = useRef<any>(null);

  const history = useQuery({ queryKey: ["chat-history"], queryFn: () => apiGet<ChatMessage[]>("/chat/history") });

  useEffect(() => {
    (async () => {
      setToken(await getToken());
      try {
        if (Platform.OS !== "web") {
          await AudioModule.requestRecordingPermissionsAsync();
        }
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
      } catch (e) { console.warn(e); }
    })();
    return () => {
      try { playerRef.current?.remove?.(); } catch {}
    };
  }, []);

  useEffect(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [history.data?.length]);

  async function playTTS(text: string) {
    try {
      const t = token ?? (await getToken());
      const resp = await fetch(`${API_BASE}/api/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
        body: JSON.stringify({ text, voice: "onyx" }),
      });
      if (!resp.ok) return;
      const data = await resp.json();
      const url = `${API_BASE}${data.url}`;
      try { playerRef.current?.remove?.(); } catch {}
      const player = createAudioPlayer({ uri: url });
      playerRef.current = player;
      player.play();
    } catch (e) { console.warn("TTS failed", e); }
  }

  async function sendText(text: string) {
    if ((!text.trim() && !pendingPhoto) || busy) return;
    setBusy(true);
    try {
      const body: any = { content: text || "(photo attached)" };
      if (pendingPhoto) body.photo_url = pendingPhoto.url;
      const resp = await apiPost<{ ai_message: ChatMessage; route_hint?: string }>("/chat/send", body);
      setPendingPhoto(null);
      await qc.invalidateQueries({ queryKey: ["chat-history"] });
      await qc.invalidateQueries({ queryKey: ["digest"] });
      await qc.invalidateQueries({ queryKey: ["change-orders"] });
      await qc.invalidateQueries({ queryKey: ["back-charges"] });
      await qc.invalidateQueries({ queryKey: ["missed-money"] });
      if (resp.ai_message?.content) playTTS(resp.ai_message.content);
      // Voice kickoff routing
      if (resp.route_hint === "/checkin") {
        setTimeout(() => router.push("/checkin"), 600);
      }
    } catch (e: any) {
      console.warn("send failed", e);
    } finally { setBusy(false); }
  }

  async function pickPhoto() {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        console.warn("photo permission denied");
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.7,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      setBusy(true);
      const uploaded = await uploadPhoto(asset.uri);
      setPendingPhoto({ url: uploaded.url, localUri: asset.uri });
    } catch (e) {
      console.warn("photo pick failed", e);
    } finally { setBusy(false); }
  }

  async function takePhoto() {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        console.warn("camera permission denied");
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ["images"],
        quality: 0.7,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      setBusy(true);
      const uploaded = await uploadPhoto(asset.uri);
      setPendingPhoto({ url: uploaded.url, localUri: asset.uri });
    } catch (e) {
      console.warn("camera failed", e);
    } finally { setBusy(false); }
  }

  async function startRecording() {
    try {
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) { console.warn("record start failed", e); }
  }

  async function stopAndSend() {
    try {
      await recorder.stop();
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
      const uri = recorder.uri;
      if (!uri) return;
      setBusy(true);
      const { text } = await uploadAudio(uri);
      if (text || pendingPhoto) await sendText(text);
    } catch (e: any) {
      console.warn("transcribe failed", e);
    } finally { setBusy(false); }
  }

  const suggestions = [
    "Wrap it up for the day",
    "GC added extra work on east wall",
    "Failed inspection on Maple Street",
    "GC's back-charging $800 for cleanup",
  ];

  function photoSrc(url: string): { uri: string; headers?: Record<string, string> } {
    if (Platform.OS === "web") {
      return { uri: `${API_BASE}${url}?token=${encodeURIComponent(token || "")}` };
    }
    return { uri: `${API_BASE}${url}`, headers: token ? { Authorization: `Bearer ${token}` } : undefined };
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top, backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}>
        <Text style={{ color: colors.brandPrimary, fontSize: 11, fontWeight: "900", letterSpacing: 2 }}>AI FOREMAN</Text>
        <Text style={{ color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "900" }}>Talk to SubSidekick</Text>
      </View>

      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
      >
        {history.isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (history.data?.length ?? 0) === 0 ? (
          <View style={{ alignItems: "center", paddingVertical: spacing.xxl }}>
            <View style={{ width: 88, height: 88, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.borderStrong }}>
              <Icon name="microphone" size={44} color={colors.onBrandPrimary} />
            </View>
            <Text style={{ marginTop: spacing.md, color: colors.onSurface, fontSize: 20, fontWeight: "900" }}>TAP AND HOLD TO TALK</Text>
            <Text style={{ marginTop: 6, color: colors.muted, fontSize: 14, textAlign: "center", paddingHorizontal: spacing.lg }}>
              Report change orders, back charges, failed inspections. Add a photo. The office reviews it.
            </Text>
          </View>
        ) : (
          (history.data ?? []).map((m) => (
            <View key={m.id} testID={`msg-${m.id}`}
              style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "88%", marginBottom: spacing.sm }}>
              <View style={{
                backgroundColor: m.role === "user" ? colors.surfaceInverse : colors.brandTertiary,
                borderWidth: 2, borderColor: colors.borderStrong, padding: spacing.md,
              }}>
                <Text style={{
                  color: m.role === "user" ? colors.onSurfaceInverse : colors.onBrandTertiary,
                  fontSize: 16, fontWeight: "500", lineHeight: 22,
                }}>
                  {m.content}
                </Text>
              </View>
              <Text style={{ fontSize: 10, color: colors.muted, marginTop: 4, textAlign: m.role === "user" ? "right" : "left", fontWeight: "700", letterSpacing: 1 }}>
                {m.role === "user" ? "YOU" : "AI FOREMAN"}
              </Text>
            </View>
          ))
        )}
        {busy && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.sm }}>
            <ActivityIndicator size="small" color={colors.brandPrimary} />
            <Text style={{ color: colors.muted, fontWeight: "700" }}>Working…</Text>
          </View>
        )}
      </ScrollView>

      {/* Suggestion chips — always visible */}
      <View style={{ borderTopWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm, paddingVertical: spacing.sm, height: 56, alignItems: "center" }}>
          {suggestions.map((s, i) => (
            <Pressable key={i} testID={`suggestion-${i}`} onPress={() => sendText(s)}
              style={{
                height: 40, paddingHorizontal: spacing.md, justifyContent: "center",
                borderWidth: 2, borderColor: colors.borderStrong,
                backgroundColor: i === 0 ? colors.brandTertiary : colors.surface,
                flexShrink: 0,
              }}>
              <Text style={{ color: colors.onSurface, fontSize: 12, fontWeight: "800" }} numberOfLines={1}>"{s}"</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {/* Pending photo preview */}
      {pendingPhoto && (
        <View style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderTopWidth: 2, borderColor: colors.borderStrong }}>
          <View style={{ paddingTop: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Image testID="pending-photo" source={{ uri: pendingPhoto.localUri }} style={{ width: 56, height: 56, borderWidth: 2, borderColor: colors.borderStrong }} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.onSurface, fontWeight: "900", fontSize: 12, letterSpacing: 1 }}>PHOTO ATTACHED</Text>
              <Text style={{ color: colors.muted, fontSize: 12 }}>Will attach to your next message.</Text>
            </View>
            <Pressable testID="remove-photo" onPress={() => setPendingPhoto(null)} hitSlop={12}>
              <Icon name="close" size={24} color={colors.onSurface} />
            </Pressable>
          </View>
        </View>
      )}

      {/* Bottom action row */}
      <View style={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.lg, backgroundColor: colors.surface, borderTopWidth: 2, borderColor: colors.borderStrong }}>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <Pressable
            testID="take-photo-btn"
            onPress={takePhoto}
            disabled={busy}
            style={({ pressed }) => ({
              width: 64, minHeight: 88,
              backgroundColor: pressed ? colors.surfaceInverse : colors.surface,
              borderWidth: 2, borderColor: colors.borderStrong,
              alignItems: "center", justifyContent: "center",
            })}
          >
            <Icon name="camera" size={26} color={colors.onSurface} />
            <Text style={{ color: colors.onSurface, fontSize: 9, fontWeight: "900", letterSpacing: 1, marginTop: 2 }}>SNAP</Text>
          </Pressable>
          <Pressable
            testID="attach-photo-btn"
            onPress={pickPhoto}
            disabled={busy}
            style={({ pressed }) => ({
              width: 64, minHeight: 88,
              backgroundColor: pressed ? colors.surfaceInverse : colors.surface,
              borderWidth: 2, borderColor: colors.borderStrong,
              alignItems: "center", justifyContent: "center",
            })}
          >
            <Icon name="image-multiple" size={26} color={colors.onSurface} />
            <Text style={{ color: colors.onSurface, fontSize: 9, fontWeight: "900", letterSpacing: 1, marginTop: 2 }}>GALLERY</Text>
          </Pressable>
          <Pressable
            testID="ptt-button"
            onPressIn={startRecording}
            onPressOut={stopAndSend}
            disabled={busy}
            style={({ pressed }) => ({
              flex: 1,
              backgroundColor: (recState.isRecording || pressed) ? colors.surfaceInverse : colors.brandPrimary,
              borderWidth: 2,
              borderColor: colors.borderStrong,
              minHeight: 88,
              alignItems: "center",
              justifyContent: "center",
              flexDirection: "row",
              gap: spacing.sm,
              opacity: busy ? 0.6 : 1,
            })}
          >
            <Icon name={recState.isRecording ? "record-circle" : "microphone"} size={30} color={recState.isRecording ? colors.brandPrimary : colors.onBrandPrimary} />
            <Text style={{ color: recState.isRecording ? colors.onSurfaceInverse : colors.onBrandPrimary, fontSize: 16, fontWeight: "900", letterSpacing: 1 }}>
              {recState.isRecording ? "RELEASE" : "HOLD TO TALK"}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}
