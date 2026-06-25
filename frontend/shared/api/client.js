const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_PREFIX = "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const API_KEY_HEADER = import.meta.env.VITE_API_KEY_HEADER ?? "x-api-key";
const AUTH_TOKEN_KEY = "hf_cdss_auth_token";

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

export function apiUrl(path) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized.startsWith("/api/auth")) {
    return `${API_BASE_URL}${normalized}`;
  }
  if (normalized.startsWith("/api/v1")) {
    return `${API_BASE_URL}${normalized}`;
  }
  return `${API_BASE_URL}${API_PREFIX}${normalized}`;
}

export function apiHeaders(extra = {}) {
  const headers = { ...extra };
  if (API_KEY) headers[API_KEY_HEADER] = API_KEY;
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
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
  const headers = apiHeaders();
  const response = await fetch(apiUrl(path), { method: "GET", headers });
  return parseResponse(response);
}

export async function apiPost(path, body, options = {}) {
  const headers = apiHeaders({ "Content-Type": "application/json" });
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parseResponse(response);
}

export async function apiPatch(path, body) {
  const headers = apiHeaders({ "Content-Type": "application/json" });
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

export async function apiPostForm(path, formData) {
  const headers = apiHeaders();
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: formData,
  });
  return parseResponse(response);
}

export async function login(username, password) {
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const data = await apiPostForm("/auth/login", form);
  setAuthToken(data.access_token);
  return data;
}

export async function fetchCurrentUser() {
  return apiGet("/auth/me");
}

export async function logout() {
  try {
    await apiPost("/auth/logout");
  } finally {
    setAuthToken(null);
  }
}

export { API_BASE_URL, API_PREFIX, API_KEY, API_KEY_HEADER };
