import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [token, setToken]     = useState(() => localStorage.getItem('sentinel_token'));
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');

  const fetchMe = useCallback(async (t) => {
    if (!t) {
      setLoading(false);
      return;
    }
    try {
      const r = await fetch(`${API}/api/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (r.ok) {
        const d = await r.json();
        setUser(d.user);
      } else {
        localStorage.removeItem('sentinel_token');
        setToken(null);
        setUser(null);
      }
    } catch {
      // Бэкенд недоступен — сбрасываем токен чтобы показать форму входа
      localStorage.removeItem('sentinel_token');
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMe(token); }, [token, fetchMe]);

  const login = async (username, password) => {
    setError('');
    try {
      const r = await fetch(`${API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const d = await r.json();
      if (!r.ok) { setError(d.detail || 'Ошибка входа'); return false; }
      localStorage.setItem('sentinel_token', d.token);
      setToken(d.token);
      setUser(d.user);
      return true;
    } catch {
      setError('Бэкенд недоступен (порт 8000)');
      return false;
    }
  };

  const register = async (username, password, email) => {
    setError('');
    try {
      const r = await fetch(`${API}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, email }),
      });
      const d = await r.json();
      if (!r.ok) { setError(d.detail || 'Ошибка регистрации'); return false; }
      localStorage.setItem('sentinel_token', d.token);
      setToken(d.token);
      setUser(d.user);
      return true;
    } catch {
      setError('Бэкенд недоступен (порт 8000)');
      return false;
    }
  };

  const logout = () => {
    localStorage.removeItem('sentinel_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, error, login, register, logout, setError }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);