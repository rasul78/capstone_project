import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';

const ACCENT = '#2563EB';
const ACCENT_LIGHT = '#EFF6FF';
const BORDER = '#E2E8F0';
const MUTED = '#94A3B8';

export default function AuthPage() {
  const { login, register, error, setError } = useAuth();
  const [mode, setMode]         = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail]       = useState('');
  const [busy, setBusy]         = useState(false);
  const [showPass, setShowPass] = useState(false);

  const handleSubmit = async () => {
    if (!username.trim() || !password.trim()) return;
    setBusy(true);
    await (mode === 'login'
      ? login(username.trim(), password)
      : register(username.trim(), password, email.trim()));
    setBusy(false);
  };

  const switchMode = (m) => { setMode(m); setError(''); setUsername(''); setPassword(''); setEmail(''); };

  const inp = {
    width: '100%', padding: '11px 14px', fontSize: 14,
    border: `1.5px solid ${BORDER}`, borderRadius: 10, outline: 'none',
    fontFamily: "'Inter', sans-serif", color: '#0F172A',
    background: '#fff', boxSizing: 'border-box', transition: 'border-color .15s',
  };

  const onFocus = e => { e.target.style.borderColor = ACCENT; };
  const onBlur  = e => { e.target.style.borderColor = BORDER; };

  return (
    <div style={{
      minHeight: '100vh', background: 'linear-gradient(135deg, #F8FAFF 0%, #EFF6FF 50%, #F0FDF4 100%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: "'Inter', sans-serif",
    }}>
      {/* Left hero */}
      <div style={{ flex: 1, maxWidth: 500, padding: '60px 60px', display: 'none' }}>
      </div>

      {/* Card */}
      <div style={{
        background: '#fff', borderRadius: 20, padding: '48px 40px',
        width: '100%', maxWidth: 420,
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.07), 0 20px 60px rgba(37,99,235,0.08)',
        border: `1px solid ${BORDER}`,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'linear-gradient(135deg, #2563EB, #7C3AED)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20,
          }}>🛡</div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', letterSpacing: '-0.02em' }}>Sentinel AI</div>
            <div style={{ fontSize: 12, color: MUTED }}>Multi-Agent Platform</div>
          </div>
        </div>

        {/* Tabs */}
        <div style={{
          display: 'flex', background: '#F1F5F9', borderRadius: 10, padding: 4,
          marginBottom: 28, gap: 4,
        }}>
          {[['login','Войти'],['register','Регистрация']].map(([m, label]) => (
            <button key={m} onClick={() => switchMode(m)} style={{
              flex: 1, padding: '8px 0', borderRadius: 7, border: 'none',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', transition: 'all .15s',
              fontFamily: "'Inter', sans-serif",
              background: mode === m ? '#fff' : 'transparent',
              color: mode === m ? '#0F172A' : MUTED,
              boxShadow: mode === m ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
            }}>{label}</button>
          ))}
        </div>

        <div style={{ fontSize: 22, fontWeight: 700, color: '#0F172A', marginBottom: 6, letterSpacing: '-0.02em' }}>
          {mode === 'login' ? 'Добро пожаловать' : 'Создать аккаунт'}
        </div>
        <div style={{ fontSize: 13, color: MUTED, marginBottom: 24 }}>
          {mode === 'login' ? 'Войдите, чтобы продолжить работу с платформой' : 'Заполните данные для регистрации'}
        </div>

        {/* Fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6, letterSpacing: '0.02em' }}>
              ЛОГИН
            </label>
            <input
              value={username} onChange={e => setUsername(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              onFocus={onFocus} onBlur={onBlur}
              placeholder="username" style={inp}
            />
          </div>

          {mode === 'register' && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6, letterSpacing: '0.02em' }}>
                EMAIL (необязательно)
              </label>
              <input
                value={email} onChange={e => setEmail(e.target.value)}
                onFocus={onFocus} onBlur={onBlur}
                placeholder="you@example.com" type="email" style={inp}
              />
            </div>
          )}

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6, letterSpacing: '0.02em' }}>
              ПАРОЛЬ
            </label>
            <div style={{ position: 'relative' }}>
              <input
                value={password} onChange={e => setPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                onFocus={onFocus} onBlur={onBlur}
                type={showPass ? 'text' : 'password'}
                placeholder="••••••••" style={{ ...inp, paddingRight: 44 }}
              />
              <button onClick={() => setShowPass(!showPass)} style={{
                position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', cursor: 'pointer', fontSize: 16,
                color: MUTED, padding: 4,
              }}>{showPass ? '🙈' : '👁'}</button>
            </div>
          </div>

          {error && (
            <div style={{
              padding: '10px 14px', borderRadius: 8, fontSize: 13,
              background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626',
            }}>{error}</div>
          )}

          <button onClick={handleSubmit} disabled={busy || !username.trim() || !password.trim()} style={{
            width: '100%', padding: '12px', borderRadius: 10, border: 'none',
            fontSize: 14, fontWeight: 600, cursor: busy ? 'wait' : 'pointer',
            fontFamily: "'Inter', sans-serif", letterSpacing: '-0.01em',
            background: busy || !username.trim() || !password.trim()
              ? '#E2E8F0' : 'linear-gradient(135deg, #2563EB, #7C3AED)',
            color: busy || !username.trim() || !password.trim() ? MUTED : '#fff',
            transition: 'all .15s', marginTop: 4,
            boxShadow: busy || !username.trim() || !password.trim() ? 'none' : '0 4px 14px rgba(37,99,235,0.3)',
          }}>
            {busy ? '⏳ Загрузка...' : mode === 'login' ? '→ Войти' : '→ Зарегистрироваться'}
          </button>
        </div>

        {/* Demo hint */}
        <div style={{
          marginTop: 24, padding: '12px 16px', borderRadius: 10,
          background: ACCENT_LIGHT, border: `1px solid #BFDBFE`,
        }}>
          <div style={{ fontSize: 12, color: '#1D4ED8', fontWeight: 600, marginBottom: 4 }}>💡 Demo аккаунты</div>
          <div style={{ fontSize: 11.5, color: '#3B82F6', lineHeight: 1.6 }}>
            <strong>demo</strong> / demo123 &nbsp;·&nbsp; <strong>admin</strong> / admin123
          </div>
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::placeholder { color: #CBD5E1; }
      `}</style>
    </div>
  );
}