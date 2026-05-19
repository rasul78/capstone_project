import React, { useEffect, useState } from 'react';
import { useStore } from './store/index';
import TrainPage    from './pages/TrainPage';
import PredictPage  from './pages/PredictPage';
import ArchPage     from './pages/ArchPage';
import DocsChatPage from './pages/DocsChatPage';

const MONO = "'JetBrains Mono', monospace";

const NAV = [
  { id: 'docs',    icon: '🧠', label: 'База знаний',   sub: 'RAG · PostgreSQL' },
  { id: 'train',   icon: '⚡', label: 'Обучение',       sub: 'CNN · PyTorch'   },
  { id: 'predict', icon: '◎',  label: 'Распознавание',  sub: 'VisionNet'       },
  { id: 'arch',    icon: '⬡',  label: 'Архитектура',    sub: 'ResNet + SE'     },
];

function SidebarItem({ item, active, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: '100%', background: active
          ? 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(124,58,237,0.12))'
          : hov ? 'rgba(255,255,255,0.03)' : 'transparent',
        border: active ? '1px solid rgba(99,102,241,0.25)' : '1px solid transparent',
        borderRadius: 12, padding: '12px 14px',
        cursor: 'pointer', textAlign: 'left', transition: 'all .2s',
        display: 'flex', alignItems: 'center', gap: 12,
      }}
    >
      <span style={{
        width: 34, height: 34, borderRadius: 9, flexShrink: 0,
        background: active
          ? 'linear-gradient(135deg,#4f46e5,#7c3aed)'
          : 'rgba(255,255,255,0.04)',
        border: active ? 'none' : '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16,
        boxShadow: active ? '0 4px 12px rgba(99,102,241,0.4)' : 'none',
      }}>{item.icon}</span>
      <div>
        <div style={{
          fontSize: 13, fontWeight: active ? 700 : 500,
          color: active ? '#e2e8f8' : 'rgba(255,255,255,0.4)',
          lineHeight: 1.2,
        }}>{item.label}</div>
        <div style={{
          fontSize: 10, color: active ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.15)',
          fontFamily: MONO, marginTop: 2,
        }}>{item.sub}</div>
      </div>
    </button>
  );
}

export default function App() {
  const [page, setPage] = useState('docs');
  const { kbStats, fetchKbDocs, fetchModelInfo, fetchStatus } = useStore();

  useEffect(() => {
    fetchKbDocs();
    fetchModelInfo();
    fetchStatus();
    const t = setInterval(fetchStatus, 3000);
    return () => clearInterval(t);
  }, [fetchKbDocs, fetchModelInfo, fetchStatus]);

  const pages = { train: TrainPage, predict: PredictPage, arch: ArchPage, docs: DocsChatPage };
  const Page  = pages[page];

  return (
    <div style={{
      display: 'flex', height: '100vh', width: '100vw',
      background: '#080a12',
      fontFamily: "'Manrope', sans-serif",
      color: '#e2e8f8',
      overflow: 'hidden',
    }}>
      {/* ── Sidebar ── */}
      <div style={{
        width: 220, flexShrink: 0,
        background: 'rgba(10,12,20,0.95)',
        borderRight: '1px solid rgba(255,255,255,0.04)',
        display: 'flex', flexDirection: 'column',
        padding: '0 12px 16px',
      }}>
        {/* Logo */}
        <div style={{ padding: '22px 6px 20px', borderBottom: '1px solid rgba(255,255,255,0.04)', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg,#4f46e5,#7c3aed)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18, boxShadow: '0 4px 16px rgba(99,102,241,0.5)',
            }}>🛡</div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em' }}>Sentinel</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', fontFamily: MONO }}>AI Platform v3</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
          {NAV.map(item => (
            <SidebarItem key={item.id} item={item} active={page === item.id} onClick={() => setPage(item.id)} />
          ))}
        </div>

        {/* DB status */}
        <div style={{
          padding: '12px 14px', borderRadius: 12,
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.04)',
        }}>
          <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.15)', fontFamily: MONO, letterSpacing: '0.1em', marginBottom: 8 }}>
            POSTGRESQL
          </div>
          {[
            ['Документов', kbStats?.total_docs ?? '—'],
            ['Фрагментов', kbStats?.total_chunks ?? '—'],
            ['Embeddings', kbStats?.embedding_dim ? `${kbStats.embedding_dim}d` : '128d'],
          ].map(([k, v]) => (
            <div key={k} style={{
              display: 'flex', justifyContent: 'space-between',
              fontSize: 11, marginBottom: 4,
            }}>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>{k}</span>
              <span style={{ color: '#6366f1', fontFamily: MONO, fontWeight: 600 }}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22d3a5', display: 'inline-block', boxShadow: '0 0 6px #22d3a5' }} />
            <span style={{ fontSize: 10, color: '#22d3a5', fontFamily: MONO }}>connected</span>
          </div>
        </div>
      </div>

      {/* ── Main content ── */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Page />
      </div>

      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
