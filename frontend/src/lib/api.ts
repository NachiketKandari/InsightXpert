import { API_BASE_URL } from "./constants";

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
}

export async function apiCall<T>(path: string, options?: RequestInit): Promise<T | null> {
  try {
    const res = await apiFetch(path, options);
    if (!res.ok) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}
