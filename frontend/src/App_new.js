import React, { useEffect, useState } from 'react';
import { useStore } from './store/index';
import { useAuth } from './contexts/AuthContext';
import AuthPage from './pages/new/AuthPage';
import TrainPage    from './pages/TrainPage';
import PredictPage  from './pages/PredictPage';
import ArchPage     from './pages/ArchPage';
import DocsChatPage from './pages/DocsChatPage';
import ChatHistoryPage from './pages/new/ChatHistoryPage';

const NAV = [
  { id: 'docs',    icon: '🧠', label: 'Ассистент',    sub: 'RAG · Multi-Agent'  },
  { id: 'history', icon: '💬', label: 'История чатов', sub: 'PostgreSQL'         },
  { id: 'predict', icon: '🔍', label: 'Распознавание', sub: 'VisionNet CNN'      },
  { id: 'train',   icon: '⚡', label: 'Обучение',      sub: 'PyTorch'            },
  { id: 'arch',    icon: '⬡',  label: 'Архитектура',   sub: 'ResNet + SE'        },
];

function NavItem({ item, active, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: '100%', background: active ? '#EFF6FF' : hov ? '#F8FAFC' : 'transparent',
        border: active ? '1.5px solid #BFDBFE' : '1.5px solid transparent',
        borderRadius: 10, padding: '10px 12px',
        cursor: 'pointer', textAlign: 'left', transition: 'all .15s',
        display: 'flex', alignItems: 'center', gap: 10,
      }}
    >
      <span style={{
        width: 34, height: 34, borderRadius: 9, flexShrink: 0,
        background: active ? 'linear-gradient(135deg,#2563EB,#7C3AED)' : '#F1F5F9',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16, boxShadow: active ? '0 3px 10px rgba(37,99,235,0.3)' : 'none',
      }}>{item.icon}</span>
      <div>
        <div style={{ fontSize: 13, fontWeight: active ? 700 : 500, color: active ? '#1E40AF' : '#374151', lineHeight: 1.2 }}>
          {item.label}
        </div>
        <div style={{ fontSize: 10, color: active ? '#60A5FA' : '#94A3B8', marginTop: 2, fontFamily: "'JetBrains Mono', monospace" }}>
          {item.sub}
        </div>
      </div>
      {active && <div style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: '#2563EB' }} />}
    </button>
  );
}

export default function App() {
  const { user, logout, loading } = useAuth();
  const [page, setPage] = useState('docs');
  const { kbStats, fetchKbDocs, fetchModelInfo, fetchStatus } = useStore();

  useEffect(() => {
    if (user) {
      fetchKbDocs();
      fetchModelInfo();
      fetchStatus();
      const t = setInterval(fetchStatus, 3000);
      return () => clearInterval(t);
    }
  }, [user, fetchKbDocs, fetchModelInfo, fetchStatus]);

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F8FAFC', fontFamily: "'Inter', sans-serif" }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🛡</div>
          <div style={{ fontSize: 14, color: '#94A3B8' }}>Загрузка Sentinel AI...</div>
        </div>
      </div>
    );
  }

  if (!user) return <AuthPage />;

  const pages = { train: TrainPage, predict: PredictPage, arch: ArchPage, docs: DocsChatPage, history: ChatHistoryPage };
  const Page = pages[page] || DocsChatPage;

  return (
    <div style={{
      display: 'flex', height: '100vh', width: '100vw',
      background: '#F8FAFC',
      fontFamily: "'Inter', sans-serif",
      color: '#0F172A', overflow: 'hidden',
    }}>
      {/* Sidebar */}
      <div style={{
        width: 230, flexShrink: 0,
        background: '#FFFFFF',
        borderRight: '1px solid #E2E8F0',
        display: 'flex', flexDirection: 'column',
        padding: '0 12px 16px',
        boxShadow: '2px 0 8px rgba(0,0,0,0.04)',
      }}>
        {/* Logo */}
        <div style={{ padding: '20px 6px 18px', borderBottom: '1px solid #F1F5F9', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'linear-gradient(135deg, #2563EB, #7C3AED)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18, boxShadow: '0 4px 12px rgba(37,99,235,0.3)',
            }}>🛡</div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', color: '#0F172A' }}>Sentinel</div>
              <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: "'JetBrains Mono', monospace" }}>AI Platform v4.0</div>
            </div>
          </div>
        </div>

        {/* User badge */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
          background: '#F0FDF4', borderRadius: 10, border: '1px solid #BBF7D0',
          marginBottom: 14,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg,#059669,#10B981)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, color: '#fff', fontWeight: 700,
          }}>{user.username[0].toUpperCase()}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#065F46', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.username}
            </div>
            <div style={{ fontSize: 10, color: '#34D399' }}>{user.role}</div>
          </div>
          <button onClick={logout} style={{
            background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#6EE7B7', padding: 2,
          }} title="Выйти">↩</button>
        </div>

        {/* Nav */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, flex: 1 }}>
          {NAV.map(item => (
            <NavItem key={item.id} item={item} active={page === item.id} onClick={() => setPage(item.id)} />
          ))}
        </div>

        {/* DB stats */}
        <div style={{
          padding: '12px 14px', borderRadius: 12,
          background: '#F8FAFC', border: '1px solid #E2E8F0',
        }}>
          <div style={{ fontSize: 9, color: '#94A3B8', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.1em', marginBottom: 8 }}>
            POSTGRESQL · БД
          </div>
          {[
            ['Документов', kbStats?.total_docs ?? '—'],
            ['Фрагментов', kbStats?.total_chunks ?? '—'],
            ['Размерность', kbStats?.embedding_dim ? `${kbStats.embedding_dim}d` : '384d'],
          ].map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
              <span style={{ color: '#94A3B8' }}>{k}</span>
              <span style={{ color: '#2563EB', fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
            <span style={{ fontSize: 10, color: '#10B981', fontFamily: "'JetBrains Mono', monospace" }}>connected</span>
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Page />
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        body { margin: 0; background: #F8FAFC; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #E2E8F0; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #CBD5E1; }
        button { font-family: inherit; }
        input, textarea, select { font-family: inherit; }
      `}</style>
    </div>
  );
}
