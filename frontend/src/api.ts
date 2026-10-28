import { Platform } from "react-native";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

export const API = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(msg);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const txt = await res.text();
  let data: any = null;
  try {
    data = txt ? JSON.parse(txt) : null;
  } catch {
    data = txt;
  }
  if (!res.ok) {
    const d = data?.detail;
    throw new ApiError(res.status, typeof d === "string" ? d : JSON.stringify(d ?? data));
  }
  return data as T;
}

export async function downloadAndShare(url: string, filename: string) {
  if (Platform.OS === "web") {
    (globalThis as any).open?.(url, "_blank");
    return "opened";
  }
  const target = new File(Paths.cache, filename);
  if (target.exists) target.delete();
  const out = await File.downloadFileAsync(url, target);
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(out.uri);
  return out.uri;
}
