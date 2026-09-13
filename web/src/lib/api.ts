const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'mars_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function extractDetailMessage(body) {
  if (!body) return null;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((d) => `${(d.loc || []).join('.')}: ${d.msg}`).join(' / ');
  }
  if (body.message) return body.message;
  return null;
}

async function handleResponse(res) {
  if (!res.ok) {
    let message = `요청에 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      const detail = extractDetailMessage(body);
      if (detail) message = detail;
    } catch {
    }
    throw new ApiError(message, res.status);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : undefined;
}

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  return handleResponse(res);
}

export async function apiFetchForm(path, formFields) {
  const body = new URLSearchParams();
  Object.entries(formFields).forEach(([key, value]) => body.set(key, value));
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  return handleResponse(res);
}
