import { Platform } from "react-native";
import { getToken } from "./auth/token-store";

export const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

let inMemoryToken: string | null = null;

export function setInMemoryToken(t: string | null) {
  inMemoryToken = t;
}

async function authHeaders(): Promise<Record<string, string>> {
  const t = inMemoryToken ?? (await getToken());
  if (t) return { Authorization: `Bearer ${t}` };
  return {};
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/api${path}`, { headers });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiPost<T>(path: string, body?: any): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiPatch<T>(path: string, body?: any): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "PATCH",
    headers: { ...headers, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiDelete<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function uploadAudio(uri: string): Promise<{ text: string }> {
  const headers = await authHeaders();
  const form = new FormData();
  const isWeb = Platform.OS === "web";
  const name = isWeb ? "recording.webm" : "recording.m4a";
  const type = isWeb ? "audio/webm" : "audio/mp4";
  if (isWeb) {
    const blob = await (await fetch(uri)).blob();
    // @ts-ignore
    form.append("file", new File([blob], name, { type }));
  } else {
    // @ts-ignore
    form.append("file", { uri, name, type });
  }
  const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
    method: "POST",
    headers, // do NOT set Content-Type; boundary
    body: form,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function uploadPhoto(uri: string): Promise<{ storage_path: string; url: string }> {
  const headers = await authHeaders();
  const form = new FormData();
  const isWeb = Platform.OS === "web";
  const name = "photo.jpg";
  const type = "image/jpeg";
  if (isWeb) {
    const blob = await (await fetch(uri)).blob();
    // @ts-ignore
    form.append("file", blob, name);
  } else {
    // @ts-ignore
    form.append("file", { uri, name, type });
  }
  const res = await fetch(`${API_BASE}/api/uploads/photo`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

