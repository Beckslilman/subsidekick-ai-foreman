import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const KEY = "subsidekick_session_token";

export async function saveToken(token: string) {
  if (Platform.OS === "web") {
    try { window.localStorage.setItem(KEY, token); } catch {}
    return;
  }
  await SecureStore.setItemAsync(KEY, token);
}

export async function getToken(): Promise<string | null> {
  if (Platform.OS === "web") {
    try { return window.localStorage.getItem(KEY); } catch { return null; }
  }
  return SecureStore.getItemAsync(KEY);
}

export async function clearToken() {
  if (Platform.OS === "web") {
    try { window.localStorage.removeItem(KEY); } catch {}
    return;
  }
  await SecureStore.deleteItemAsync(KEY);
}
