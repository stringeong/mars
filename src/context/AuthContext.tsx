import { createContext, useContext, useState, ReactNode } from 'react';
import type { User } from '@/types';

/**
 * There is no real backend here, so "accounts" are persisted to localStorage
 * as a stand-in for a users table. This is a frontend/demo concern only —
 * a real deployment would replace login/signup with actual API calls and
 * never store plaintext passwords client-side.
 */
interface StoredAccount {
  id: string;
  name: string;
  email: string;
  password: string;
  plan: User['plan'];
  avatarInitials: string;
}

const ACCOUNTS_KEY = 'mars_accounts';

function initialsFromName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'U';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function loadAccounts(): StoredAccount[] {
  try {
    const raw = localStorage.getItem(ACCOUNTS_KEY);
    if (raw) return JSON.parse(raw) as StoredAccount[];
  } catch {
    // Corrupted storage — fall through and reseed.
  }
  // Seed one demo account so the app can be tried without signing up first.
  const seeded: StoredAccount[] = [
    {
      id: 'u-demo',
      name: '박상인',
      email: 'demo@mars-app.dev',
      password: 'demo1234',
      plan: 'Pro',
      avatarInitials: 'AK',
    },
  ];
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(seeded));
  return seeded;
}

function saveAccounts(accounts: StoredAccount[]) {
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
}

function toUser(account: StoredAccount): User {
  return { id: account.id, name: account.name, email: account.email, plan: account.plan, avatarInitials: account.avatarInitials };
}

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isNewAccount: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  updateProfile: (patch: Partial<Pick<User, 'name' | 'email'>>) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isNewAccount, setIsNewAccount] = useState(false);

  const login = async (email: string, password: string) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    const normalizedEmail = email.trim().toLowerCase();
    const account = loadAccounts().find((a) => a.email.toLowerCase() === normalizedEmail);
    if (!account) {
      throw new Error('가입되지 않은 이메일입니다. 먼저 회원가입을 진행해주세요.');
    }
    if (account.password !== password) {
      throw new Error('비밀번호가 일치하지 않습니다.');
    }
    setIsNewAccount(false);
    setUser(toUser(account));
  };

  // A brand-new account starts with no history (no devices, no executions)
  // until the user actually connects something themselves.
  const signup = async (name: string, email: string, password: string) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    const normalizedEmail = email.trim().toLowerCase();
    const accounts = loadAccounts();
    if (accounts.some((a) => a.email.toLowerCase() === normalizedEmail)) {
      throw new Error('이미 가입된 이메일입니다. 로그인을 이용해주세요.');
    }
    const newAccount: StoredAccount = {
      id: `u-${Date.now()}`,
      name: name.trim() || '새 사용자',
      email: email.trim(),
      password,
      plan: 'Free',
      avatarInitials: initialsFromName(name || email),
    };
    saveAccounts([...accounts, newAccount]);
    setIsNewAccount(true);
    setUser(toUser(newAccount));
  };

  const updateProfile = (patch: Partial<Pick<User, 'name' | 'email'>>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const updated: User = {
        ...prev,
        ...patch,
        avatarInitials: patch.name ? initialsFromName(patch.name) : prev.avatarInitials,
      };
      // Keep the stored account in sync so a future login reflects the change.
      const accounts = loadAccounts();
      const idx = accounts.findIndex((a) => a.id === prev.id);
      if (idx !== -1) {
        accounts[idx] = { ...accounts[idx], name: updated.name, email: updated.email, avatarInitials: updated.avatarInitials };
        saveAccounts(accounts);
      }
      return updated;
    });
  };

  const logout = () => setUser(null);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isNewAccount, login, signup, updateProfile, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
