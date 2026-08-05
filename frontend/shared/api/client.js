const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const API_PREFIX = "/api/v1";
export const API_FETCH_TIMEOUT_MS = 15_000;

function withCredentials(options = {}) {
  return { credentials: "include", ...options };
}

function fetchWithTimeout(url, options = {}) {
  const { timeoutMs = API_FETCH_TIMEOUT_MS, signal: userSignal, ...rest } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  if (userSignal) {
    if (userSignal.aborted) {
      controller.abort();
    } else {
      userSignal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  return fetch(url, { ...rest, signal: controller.signal }).finally(() => {
    clearTimeout(timeoutId);
  });
}

export function apiUrl(path) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized.startsWith("/api/auth")) {
    return API_BASE_URL ? `${API_BASE_URL}${normalized}` : normalized;
  }
  if (normalized.startsWith("/api/v1")) {
    return API_BASE_URL ? `${API_BASE_URL}${normalized}` : normalized;
  }
  if (normalized === "/routes" || normalized.startsWith("/routes?")) {
    return API_BASE_URL ? `${API_BASE_URL}${normalized}` : normalized;
  }
  const prefixed = `${API_PREFIX}${normalized}`;
  return API_BASE_URL ? `${API_BASE_URL}${prefixed}` : prefixed;
}

export function apiHeaders(extra = {}) {
  return { ...extra };
}

export function apiFetch(path, options = {}) {
  const { headers, timeoutMs, signal, ...rest } = options;
  return fetchWithTimeout(apiUrl(path), {
    credentials: "include",
    ...rest,
    signal,
    timeoutMs,
    headers: apiHeaders(headers),
  });
}

async function parseResponse(response) {
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const message =
      (typeof data === "object" && data?.detail) ||
      (typeof data === "object" && data?.error?.message) ||
      (typeof data === "string" ? data : null) ||
      `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

export async function apiGet(path, options = {}) {
  const { signal, timeoutMs, ...rest } = options;
  const response = await fetchWithTimeout(apiUrl(path), {
    method: "GET",
    headers: apiHeaders(),
    signal,
    timeoutMs,
    ...withCredentials(rest),
  });
  return parseResponse(response);
}

export async function apiPost(path, body, options = {}) {
  const { signal, ...rest } = options;
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
    ...withCredentials(rest),
  });
  return parseResponse(response);
}

export async function apiPatch(path, body, options = {}) {
  const { signal, ...rest } = options;
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
    ...withCredentials(rest),
  });
  return parseResponse(response);
}

export async function apiPostForm(path, formData, options = {}) {
  const { signal, ...rest } = options;
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: apiHeaders(),
    body: formData,
    signal,
    ...withCredentials(rest),
  });
  return parseResponse(response);
}

export async function apiDelete(path, options = {}) {
  const { signal, ...rest } = options;
  const response = await fetch(apiUrl(path), {
    method: "DELETE",
    headers: apiHeaders(),
    signal,
    ...withCredentials(rest),
  });
  return parseResponse(response);
}

export async function login(username, password) {
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  return apiPostForm("/auth/login", form);
}

export async function fetchCurrentUser() {
  return apiGet("/auth/me", { timeoutMs: API_FETCH_TIMEOUT_MS });
}

export async function updateMyProfile(body) {
  return apiPatch("/auth/me", body);
}

export async function uploadMyAvatar(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetchWithTimeout(apiUrl("/auth/me/avatar"), {
    method: "POST",
    credentials: "include",
    body: form,
  });
  return parseResponse(response);
}

export async function deleteMyAvatar() {
  return apiDelete("/auth/me/avatar");
}

export async function logout() {
  await apiPost("/auth/logout");
}

export { API_BASE_URL, API_PREFIX };
