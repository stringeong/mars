const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export function getToken(): string | null {
  return localStorage.getItem('mars_token')
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem('mars_token', token)
  else localStorage.removeItem('mars_token')
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  }
  if (!(options.body instanceof URLSearchParams) && options.body) {
    headers['Content-Type'] = 'application/json'
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (resp.status === 204) return undefined as T
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    const detail =
      typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail ?? resp.statusText)
    if (resp.status === 401 && !path.startsWith('/auth')) {
      setToken(null)
      window.location.href = '/login'
    }
    throw new ApiError(resp.status, detail)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  login: (username: string, password: string) =>
    request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: new URLSearchParams({ username, password }),
    }),
}
