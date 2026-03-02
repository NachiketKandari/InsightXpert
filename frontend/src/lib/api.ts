import { API_BASE_URL } from "./constants";

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const isFormData = options.body instanceof FormData;
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      // Don't set Content-Type for FormData — the browser sets it with the
      // correct multipart boundary automatically.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
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
