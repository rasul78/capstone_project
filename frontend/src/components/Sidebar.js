import React, { useState } from 'react';
import { useStore } from '../store/index';

const NAV = [
  { id: 'docs',    icon: '◈', label: 'База знаний',    sub: 'документы & чат' },
  { id: 'train',   icon: '⚡', label: 'Обучение',       sub: 'CNN · PyTorch' },
  { id: 'predict', icon: '◎', label: 'Распознавание',  sub: 'загрузи картинку' },
  { id: 'arch',    icon: '⬡', label: 'Архитектура',    sub: 'VisionNet схема' },
];

export default function Sidebar() {
  const { tab, setTab, modelInfo, trainStatus, kbStats } = useStore();
  const [collapsed, setCollapsed] = useState(false);

  const bestAcc = trainStatus?.best_val_acc || modelInfo?.best_val_acc || 0;
  const epoch   = trainStatus?.epoch || modelInfo?.current_epoch || 0;
  const params  = modelInfo?.total_params_fmt || '~2.5M';

  return (
    <aside style={{
      width: collapsed ? 60 : 220,
      background: 'rgba(8,10,18,0.98)',
      borderRight: '1px solid rgba(255,255,255,0.05)',
      display: 'flex', flexDirection: 'column',
      transition: 'width .25s cubic-bezier(.4,0,.2,1)',
      flexShrink: 0, overflow: 'hidden', position: 'relative',
    }}>
      {/* Header */}
      <div style={{
        padding: collapsed ? '18px 0' : '20px 18px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        display: 'flex', alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
      }}>
        {!collapsed && (
          <div>
            <div style={{
              fontSize: 16, fontWeight: 800, letterSpacing: '-0.03em',
              color: '#fff', lineHeight: 1.2,
            }}>
              Sentinel<span style={{
                background: 'linear-gradient(90deg,#6366f1,#a78bfa)',
                WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
              }}>AI</span>
            </div>
            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', letterSpacing: '0.15em', marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>
              NEURAL PLATFORM
            </div>
          </div>
        )}
        <button onClick={() => setCollapsed(c => !c)} style={{
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 8, width: 28, height: 28, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'rgba(255,255,255,0.3)', fontSize: 11, flexShrink: 0,
          transition: 'all .15s',
        }}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* Nav */}
      <nav style={{ padding: '10px 8px', flex: 1 }}>
        {NAV.map(item => {
          const active = tab === item.id;
          return (
            <button key={item.id} onClick={() => setTab(item.id)} title={collapsed ? item.label : undefined} style={{
              width: '100%', display: 'flex', alignItems: 'center',
              gap: collapsed ? 0 : 12,
              padding: collapsed ? '10px 0' : '9px 10px',
              justifyContent: collapsed ? 'center' : 'flex-start',
              borderRadius: 10, border: 'none', cursor: 'pointer',
              background: active ? 'rgba(99,102,241,0.12)' : 'transparent',
              marginBottom: 2, transition: 'all .15s',
              position: 'relative', overflow: 'hidden',
            }}>
              {active && (
                <span style={{
                  position: 'absolute', left: 0, top: '20%', bottom: '20%',
                  width: 3, borderRadius: '0 3px 3px 0',
                  background: 'linear-gradient(180deg,#6366f1,#a78bfa)',
                }} />
              )}
              <span style={{
                fontSize: 16, lineHeight: 1,
                color: active ? '#a78bfa' : 'rgba(255,255,255,0.25)',
                transition: 'color .15s', flexShrink: 0,
              }}>{item.icon}</span>
              {!collapsed && (
                <div style={{ textAlign: 'left' }}>
                  <div style={{
                    fontSize: 12, fontWeight: active ? 700 : 500,
                    color: active ? '#e2e8f8' : 'rgba(255,255,255,0.35)',
                    transition: 'color .15s', lineHeight: 1.3,
                  }}>{item.label}</div>
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.15)', marginTop: 1, fontFamily: 'JetBrains Mono, monospace' }}>
                    {item.sub}
                  </div>
                </div>
              )}
            </button>
          );
        })}
      </nav>

      {/* Stats */}
      {!collapsed && (
        <div style={{
          margin: '0 10px 10px',
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.04)',
          borderRadius: 12, padding: '12px 14px',
        }}>
          <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.15)', letterSpacing: '0.12em', marginBottom: 10, fontFamily: 'JetBrains Mono, monospace' }}>
            СИСТЕМА
          </div>
          {[
            { l: 'Параметры CNN',  v: params,                c: '#a78bfa' },
            { l: 'Точность',       v: bestAcc > 0 ? bestAcc + '%' : '—', c: '#22d3a5' },
            { l: 'Эпох обучено',   v: epoch || '—',           c: '#fbbf24' },
            { l: 'Документов KB',  v: kbStats?.total_docs || '—', c: '#60a5fa' },
          ].map(s => (
            <div key={s.l} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.03)',
            }}>
              <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)' }}>{s.l}</span>
              <span style={{
                fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 600, color: s.c,
              }}>{s.v}</span>
            </div>
          ))}
        </div>
      )}

      {/* Online indicator */}
      {!collapsed && (
        <div style={{
          padding: '10px 18px 14px',
          display: 'flex', alignItems: 'center', gap: 7,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', background: '#22d3a5',
            boxShadow: '0 0 6px #22d3a5', animation: 'pulse 2s infinite',
          }} />
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', fontFamily: 'JetBrains Mono, monospace' }}>
            PyTorch · CPU
          </span>
          <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>
        </div>
      )}
    </aside>
  );
}