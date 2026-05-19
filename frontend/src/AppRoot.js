import React, { useState, useEffect } from 'react';
import { useStore } from './store/index';
import TrainPage       from './pages/TrainPage';
import PredictPage     from './pages/PredictPage';
import ArchPage        from './pages/ArchPage';
import DocsChatPage    from './pages/DocsChatPage';
import ChatHistoryPage from './pages/new/ChatHistoryPage';

const API    = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const TEAL   = '#0D9488';
const TEAL_L = '#F0FDFA';
const TEAL_B = '#99F6E4';
const DARK   = '#0F172A';
const MUTED  = '#64748B';
const BORDER = '#E2E8F0';

/* ─── SVG Icon set ─────────────────────────────────────────── */
const PATHS = {
  shield:  "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  brain:   "M9.5 2a5.5 5.5 0 0 1 0 11m0-11a5.5 5.5 0 0 0 0 11m0 0v9m5-14.5a5.5 5.5 0 1 1 0 11",
  chat:    "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  search:  "M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z",
  zap:     "M13 2 3 14h9l-1 8 10-12h-9l1-8z",
  hex:     "M12 2 22 8.5v7L12 22 2 15.5v-7z",
  logout:  "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  eye:     "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  eyeoff:  "M17.94 17.94A10 10 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9 9 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M1 1l22 22",
  mail:    "M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm18 2-10 7L2 6",
  check:   "M20 6 9 17l-5-5",
  db:      "M12 2C7 2 3 3.34 3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5c0-1.66-4-3-9-3zm0 0c5 0 9 1.34 9 3M3 12c0 1.66 4 3 9 3s9-1.34 9-3M3 8.5c0 1.66 4 3 9 3s9-1.34 9-3",
  arrow:   "M5 12h14M12 5l7 7-7 7",
  upload:  "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  file:    "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  x:       "M18 6 6 18M6 6l12 12",
  scan:    "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10",
};

function Icon({ name, size = 18, color = 'currentColor', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, display: 'block', ...style }}>
      <path d={PATHS[name] || ''} />
    </svg>
  );
}

/* ─── Token helpers ─────────────────────────────────────────── */
const saveToken = (t) => localStorage.setItem('sentinel_token', t);
const loadToken = ()  => localStorage.getItem('sentinel_token') || '';
const clearToken= ()  => localStorage.removeItem('sentinel_token');

/* ─── Input style factory ───────────────────────────────────── */
const inp = (extra = {}) => ({
  width: '100%', padding: '12px 16px', fontSize: 14, borderRadius: 10, outline: 'none',
  border: `1.5px solid ${BORDER}`, background: '#FAFAFA', color: DARK,
  fontFamily: 'inherit', boxSizing: 'border-box', transition: 'border-color .18s, background .18s',
  ...extra,
});
const onFocus = e => { e.target.style.borderColor = TEAL; e.target.style.background = '#fff'; };
const onBlur  = e => { e.target.style.borderColor = BORDER; e.target.style.background = '#FAFAFA'; };

/* ─── AUTH PAGE ─────────────────────────────────────────────── */
function AuthPage({ onLogin }) {
  const [mode, setMode]       = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail]     = useState('');
  const [code, setCode]       = useState('');
  const [sentCode, setSentCode] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [err, setErr]         = useState('');
  const [info, setInfo]       = useState('');
  const [busy, setBusy]       = useState(false);

  const switchMode = (m) => { setMode(m); setErr(''); setInfo(''); };

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) { setErr('Заполните все поля'); return; }
    setBusy(true); setErr('');
    try {
      const r = await fetch(`${API}/api/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.detail || 'Неверный логин или пароль'); setBusy(false); return; }
      saveToken(d.token); onLogin(d.user);
    } catch { setErr('Сервер недоступен — запустите backend на порту 8000'); }
    setBusy(false);
  };

  const handleSendCode = async () => {
    if (!username.trim() || !password.trim() || !email.trim()) { setErr('Заполните все поля'); return; }
    if (password.length < 6) { setErr('Пароль минимум 6 символов'); return; }
    if (!/^[^@]+@[^@]+\.[^@]+$/.test(email)) { setErr('Введите корректный email'); return; }
    setBusy(true); setErr('');
    const generated = String(Math.floor(100000 + Math.random() * 900000));
    setSentCode(generated);
    try {
      await fetch(`${API}/api/auth/send-code`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), code: generated }),
      });
    } catch {}
    setInfo(`Код отправлен на ${email}. Демо-режим: ${generated}`);
    setMode('verify');
    setBusy(false);
  };

  const handleVerify = async () => {
    if (code.trim() !== sentCode) { setErr('Неверный код подтверждения'); return; }
    setBusy(true); setErr('');
    try {
      const r = await fetch(`${API}/api/auth/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password, email: email.trim() }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.detail || 'Ошибка регистрации'); setBusy(false); return; }
      saveToken(d.token); onLogin(d.user);
    } catch { setErr('Сервер недоступен'); }
    setBusy(false);
  };

  const btnStyle = (disabled) => ({
    width: '100%', padding: '13px', borderRadius: 12, border: 'none', fontSize: 14.5,
    fontWeight: 600, cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
    background: disabled ? '#E2E8F0' : `linear-gradient(135deg, ${TEAL}, #0891B2)`,
    color: disabled ? MUTED : '#fff',
    boxShadow: disabled ? 'none' : '0 4px 16px rgba(13,148,136,0.32)',
    transition: 'all .2s', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 4,
  });

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(150deg,#F0FDFA 0%,#F8FAFC 55%,#EFF6FF 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Inter',system-ui,sans-serif", padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 24, padding: '48px 44px', width: '100%', maxWidth: 430, boxShadow: '0 4px 6px rgba(0,0,0,0.04),0 20px 60px rgba(13,148,136,0.09)', border: `1px solid ${TEAL_B}` }}>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 36 }}>
          <div style={{ width: 50, height: 50, borderRadius: 14, background: `linear-gradient(135deg,${TEAL},#0891B2)`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 20px rgba(13,148,136,0.30)' }}>
            <Icon name="shield" size={23} color="#fff" />
          </div>
          <div>
            <div style={{ fontSize: 21, fontWeight: 800, color: DARK, letterSpacing: '-0.03em', lineHeight: 1 }}>Sentinel AI</div>
            <div style={{ fontSize: 12, color: MUTED, marginTop: 4, letterSpacing: '0.02em' }}>Multi-Agent Platform</div>
          </div>
        </div>

        {/* Tabs */}
        {mode !== 'verify' && (
          <div style={{ display: 'flex', background: '#F1F5F9', borderRadius: 12, padding: 4, marginBottom: 30, gap: 4 }}>
            {[['login','Войти'],['register','Регистрация']].map(([m,l]) => (
              <button key={m} onClick={() => switchMode(m)} style={{
                flex: 1, padding: '9px 0', borderRadius: 9, border: 'none', fontSize: 13.5,
                fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', transition: 'all .2s',
                background: mode === m ? '#fff' : 'transparent',
                color: mode === m ? DARK : MUTED,
                boxShadow: mode === m ? '0 1px 6px rgba(0,0,0,0.08)' : 'none',
              }}>{l}</button>
            ))}
          </div>
        )}

        {/* Heading */}
        <div style={{ marginBottom: 26 }}>
          <div style={{ fontSize: 23, fontWeight: 700, color: DARK, letterSpacing: '-0.03em', marginBottom: 6 }}>
            {mode === 'login' ? 'Добро пожаловать' : mode === 'register' ? 'Создать аккаунт' : 'Подтвердите email'}
          </div>
          <div style={{ fontSize: 13.5, color: MUTED, lineHeight: 1.6 }}>
            {mode === 'login' ? 'Войдите в свою учётную запись' : mode === 'register' ? 'Зарегистрируйтесь для доступа к платформе' : `Введите 6-значный код отправленный на ${email}`}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>

          {/* LOGIN */}
          {mode === 'login' && <>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>ЛОГИН</span>
              <input value={username} onChange={e => setUsername(e.target.value)} onKeyDown={e => e.key==='Enter' && handleLogin()} placeholder="username" style={inp()} onFocus={onFocus} onBlur={onBlur} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>ПАРОЛЬ</span>
              <div style={{ position: 'relative' }}>
                <input value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key==='Enter' && handleLogin()} type={showPass?'text':'password'} placeholder="••••••••" style={inp({ paddingRight: 46 })} onFocus={onFocus} onBlur={onBlur} />
                <button onClick={() => setShowPass(!showPass)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: MUTED, display: 'flex', padding: 0 }}>
                  <Icon name={showPass?'eyeoff':'eye'} size={17} />
                </button>
              </div>
            </label>
            {err && <div style={{ padding: '11px 14px', borderRadius: 10, background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626', fontSize: 13 }}>{err}</div>}
            <button onClick={handleLogin} disabled={busy} style={btnStyle(busy)}>
              <Icon name="arrow" size={16} color="#fff" /> {busy ? 'Загрузка...' : 'Войти'}
            </button>
          </>}

          {/* REGISTER */}
          {mode === 'register' && <>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>ЛОГИН</span>
              <input value={username} onChange={e => setUsername(e.target.value)} placeholder="username" style={inp()} onFocus={onFocus} onBlur={onBlur} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>EMAIL — на него придёт код</span>
              <div style={{ position: 'relative' }}>
                <input value={email} onChange={e => setEmail(e.target.value)} type="email" placeholder="you@example.com" style={inp({ paddingLeft: 44 })} onFocus={onFocus} onBlur={onBlur} />
                <span style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: MUTED, display:'flex' }}><Icon name="mail" size={16} /></span>
              </div>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>ПАРОЛЬ (мин. 6 символов)</span>
              <div style={{ position: 'relative' }}>
                <input value={password} onChange={e => setPassword(e.target.value)} type={showPass?'text':'password'} placeholder="••••••••" style={inp({ paddingRight: 46 })} onFocus={onFocus} onBlur={onBlur} />
                <button onClick={() => setShowPass(!showPass)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: MUTED, display: 'flex', padding: 0 }}>
                  <Icon name={showPass?'eyeoff':'eye'} size={17} />
                </button>
              </div>
            </label>
            {err && <div style={{ padding: '11px 14px', borderRadius: 10, background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626', fontSize: 13 }}>{err}</div>}
            <button onClick={handleSendCode} disabled={busy} style={btnStyle(busy)}>
              <Icon name="mail" size={16} color="#fff" /> {busy ? 'Отправка...' : 'Отправить код на email'}
            </button>
          </>}

          {/* VERIFY */}
          {mode === 'verify' && <>
            {info && <div style={{ padding: '12px 16px', borderRadius: 10, background: TEAL_L, border: `1px solid ${TEAL_B}`, fontSize: 13, color: '#0F766E', lineHeight: 1.6 }}>{info}</div>}
            <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.07em' }}>КОД ПОДТВЕРЖДЕНИЯ</span>
              <input value={code} onChange={e => setCode(e.target.value)} onKeyDown={e => e.key==='Enter' && handleVerify()} placeholder="000000" maxLength={6}
                style={{ ...inp(), fontSize: 24, letterSpacing: '0.4em', textAlign: 'center', fontWeight: 700 }} onFocus={onFocus} onBlur={onBlur} />
            </label>
            <button onClick={() => switchMode('register')} style={{ background: 'none', border: 'none', color: TEAL, fontSize: 13, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', padding: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
              ← Изменить данные
            </button>
            {err && <div style={{ padding: '11px 14px', borderRadius: 10, background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626', fontSize: 13 }}>{err}</div>}
            <button onClick={handleVerify} disabled={busy} style={btnStyle(busy)}>
              <Icon name="check" size={16} color="#fff" /> {busy ? 'Проверка...' : 'Подтвердить и войти'}
            </button>
          </>}
        </div>

        {/* Demo hint */}
        <div style={{ marginTop: 24, padding: '13px 16px', borderRadius: 12, background: TEAL_L, border: `1px solid ${TEAL_B}` }}>
          <div style={{ fontSize: 12, color: '#0F766E', fontWeight: 700, marginBottom: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="check" size={13} color="#0F766E" /> Demo аккаунты (без email)
          </div>
          <div style={{ fontSize: 12.5, color: TEAL }}><b>demo</b> / demo123 &nbsp;·&nbsp; <b>admin</b> / admin123</div>
        </div>
      </div>
    </div>
  );
}

/* ─── NAV ───────────────────────────────────────────────────── */
const NAV = [
  { id:'docs',    icon:'brain',  label:'Ассистент',     sub:'RAG · Multi-Agent' },
  { id:'history', icon:'chat',   label:'История чатов',  sub:'PostgreSQL'        },
  { id:'predict', icon:'scan',   label:'OCR — Текст',    sub:'Извлечение текста' },
  { id:'train',   icon:'zap',    label:'Обучение',       sub:'PyTorch ResNet'    },
  { id:'arch',    icon:'hex',    label:'Архитектура',    sub:'ResNet + SE'       },
];

function NavItem({ item, active, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} style={{
      width:'100%', textAlign:'left', border:'none', borderRadius:12, padding:'10px 12px',
      cursor:'pointer', transition:'all .15s', fontFamily:'inherit',
      background: active ? TEAL_L : hov ? '#F8FAFC' : 'transparent',
      display:'flex', alignItems:'center', gap:11,
      outline: active ? `2px solid ${TEAL_B}` : '2px solid transparent',
    }}>
      <span style={{ width:36, height:36, borderRadius:10, flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', background: active ? TEAL : '#F1F5F9', boxShadow: active ? '0 4px 12px rgba(13,148,136,0.28)' : 'none', transition:'all .15s' }}>
        <Icon name={item.icon} size={16} color={active ? '#fff' : MUTED} />
      </span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:13.5, fontWeight: active ? 700 : 500, color: active ? '#0F766E' : DARK, lineHeight:1.2 }}>{item.label}</div>
        <div style={{ fontSize:10.5, color: active ? TEAL : '#94A3B8', marginTop:2, fontFamily:'monospace' }}>{item.sub}</div>
      </div>
      {active && <span style={{ width:6, height:6, borderRadius:'50%', background:TEAL, flexShrink:0 }} />}
    </button>
  );
}

/* ─── MAIN APP ──────────────────────────────────────────────── */
function MainApp({ user, onLogout }) {
  const [page, setPage] = useState('docs');
  const { kbStats, fetchKbDocs, fetchModelInfo, fetchStatus } = useStore();

  useEffect(() => {
    fetchKbDocs(); fetchModelInfo(); fetchStatus();
    const t = setInterval(fetchStatus, 3000);
    return () => clearInterval(t);
  }, [fetchKbDocs, fetchModelInfo, fetchStatus]);

  const PAGES = { docs:DocsChatPage, history:ChatHistoryPage, predict:PredictPage, train:TrainPage, arch:ArchPage };
  const Page  = PAGES[page] || DocsChatPage;

  return (
    <div style={{ display:'flex', height:'100vh', width:'100vw', background:'#F8FAFC', fontFamily:"'Inter',system-ui,sans-serif", color:DARK, overflow:'hidden' }}>

      {/* Sidebar */}
      <div style={{ width:240, flexShrink:0, background:'#fff', borderRight:`1px solid ${BORDER}`, display:'flex', flexDirection:'column', padding:'0 10px 16px' }}>

        {/* Logo */}
        <div style={{ padding:'22px 8px 18px', borderBottom:`1px solid #F1F5F9`, marginBottom:12 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:42, height:42, borderRadius:12, background:`linear-gradient(135deg,${TEAL},#0891B2)`, display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 4px 14px rgba(13,148,136,0.28)' }}>
              <Icon name="shield" size={20} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize:16, fontWeight:800, color:DARK, letterSpacing:'-0.03em', lineHeight:1 }}>Sentinel</div>
              <div style={{ fontSize:10.5, color:'#94A3B8', fontFamily:'monospace', marginTop:3 }}>AI Platform v4.0</div>
            </div>
          </div>
        </div>

        {/* User */}
        <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', background:TEAL_L, borderRadius:12, border:`1px solid ${TEAL_B}`, marginBottom:14 }}>
          <div style={{ width:32, height:32, borderRadius:9, background:`linear-gradient(135deg,${TEAL},#0891B2)`, display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:13, flexShrink:0 }}>
            {(user?.username||'U')[0].toUpperCase()}
          </div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:13, fontWeight:600, color:'#0F766E', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{user?.username}</div>
            <div style={{ fontSize:10.5, color:TEAL }}>{user?.role||'user'}</div>
          </div>
          <button onClick={onLogout} title="Выйти" style={{ background:'none', border:'none', cursor:'pointer', color:TEAL, display:'flex', padding:4, borderRadius:6 }}>
            <Icon name="logout" size={16} />
          </button>
        </div>

        {/* Nav */}
        <div style={{ display:'flex', flexDirection:'column', gap:2, flex:1 }}>
          {NAV.map(item => <NavItem key={item.id} item={item} active={page===item.id} onClick={() => setPage(item.id)} />)}
        </div>

        {/* DB stats */}
        <div style={{ padding:'13px 14px', borderRadius:12, background:'#F8FAFC', border:`1px solid ${BORDER}`, marginTop:8 }}>
          <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:10 }}>
            <Icon name="db" size={13} color="#94A3B8" />
            <span style={{ fontSize:10, color:'#94A3B8', fontFamily:'monospace', letterSpacing:'0.08em' }}>POSTGRESQL</span>
          </div>
          {[['Документов', kbStats?.total_docs??'—'], ['Фрагментов', kbStats?.total_chunks??'—'], ['Векторов', kbStats?.embedding_dim?`${kbStats.embedding_dim}d`:'384d']].map(([k,v]) => (
            <div key={k} style={{ display:'flex', justifyContent:'space-between', fontSize:11.5, marginBottom:5 }}>
              <span style={{ color:MUTED }}>{k}</span>
              <span style={{ color:TEAL, fontFamily:'monospace', fontWeight:700 }}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop:10, display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ width:7, height:7, borderRadius:'50%', background:'#10B981', display:'inline-block' }} />
            <span style={{ fontSize:10.5, color:'#10B981', fontFamily:'monospace' }}>connected</span>
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
        <Page />
      </div>
    </div>
  );
}

/* ─── ROOT ──────────────────────────────────────────────────── */
export default function AppRoot() {
  const [user, setUser]       = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const token = loadToken();
    if (!token) { setChecked(true); return; }
    fetch(`${API}/api/auth/me`, { headers:{ Authorization:`Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.user) setUser(d.user); else clearToken(); })
      .catch(() => clearToken())
      .finally(() => setChecked(true));
  }, []);

  if (!checked) return (
    <div style={{ height:'100vh', background:'#F8FAFC', display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'Inter,sans-serif' }}>
      <div style={{ textAlign:'center' }}>
        <div style={{ width:52, height:52, borderRadius:14, background:`linear-gradient(135deg,${TEAL},#0891B2)`, display:'flex', alignItems:'center', justifyContent:'center', margin:'0 auto 16px', boxShadow:'0 6px 20px rgba(13,148,136,0.25)' }}>
          <Icon name="shield" size={24} color="#fff" />
        </div>
        <div style={{ fontSize:14, color:MUTED }}>Загрузка...</div>
      </div>
    </div>
  );

  if (!user) return <AuthPage onLogin={u => setUser(u)} />;
  return <MainApp user={user} onLogout={() => { clearToken(); setUser(null); }} />;
}