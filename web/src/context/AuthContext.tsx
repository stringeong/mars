import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiFetch, apiFetchForm, setToken, clearToken, getToken, ApiError } from '@/lib/api';
import type { User } from '@/types';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  updateProfile: (patch: Partial<Pick<User, 'name' | 'email'>>) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function initialsFromName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'U';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function normalizeUser(raw: any): User {
  return {
    id: String(raw.id ?? raw.user_id ?? ''),
    name: raw.name ?? raw.username ?? '',
    email: raw.email ?? '',
    plan: raw.plan ?? 'Free',
    avatarInitials: raw.avatarInitials ?? initialsFromName(raw.name ?? raw.username ?? raw.email ?? 'User'),
  };
}

function extractMessage(err: unknown, fallback: string) {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    apiFetch<any>('/auth/me')
      .then((raw) => setUser(normalizeUser(raw)))
      .catch(() => clearToken())
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    try {
      const res = await apiFetchForm<any>('/auth/login', { username, password });
      setToken(res.token ?? res.access_token);
      setUser(normalizeUser(res.user ?? res));
    } catch (err) {
      throw new Error(extractMessage(err, '로그인에 실패했습니다.'));
    }
  };

  const signup = async (name: string, email: string, password: string) => {
    try {
      const res = await apiFetch<any>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username: name, email, password }),
      });
      setToken(res.token ?? res.access_token);
      setUser(normalizeUser(res.user ?? res));
    } catch (err) {
      throw new Error(extractMessage(err, '회원가입에 실패했습니다.'));
    }
  };

  const updateProfile = async (patch: Partial<Pick<User, 'name' | 'email'>>) => {
    try {
      const updated = await apiFetch<any>('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      setUser(normalizeUser(updated));
    } catch (err) {
      throw new Error(extractMessage(err, '프로필 저장에 실패했습니다.'));
    }
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, signup, updateProfile, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
