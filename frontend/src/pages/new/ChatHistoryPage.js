import React, { useState, useEffect, useCallback } from 'react';

const API  = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const MONO = "'JetBrains Mono', monospace";

const CAT_COLORS = {
  'Безопасность': { bg: '#EFF6FF', border: '#BFDBFE', text: '#1D4ED8', dot: '#3B82F6' },
  'HR':           { bg: '#F0FDF4', border: '#BBF7D0', text: '#065F46', dot: '#10B981' },
  'Финансы':      { bg: '#FFFBEB', border: '#FDE68A', text: '#92400E', dot: '#F59E0B' },
  'Этика':        { bg: '#FDF4FF', border: '#E9D5FF', text: '#6B21A8', dot: '#A855F7' },
  'IT':           { bg: '#EFF6FF', border: '#BFDBFE', text: '#1E40AF', dot: '#60A5FA' },
  'Загружено':    { bg: '#F5F3FF', border: '#DDD6FE', text: '#5B21B6', dot: '#8B5CF6' },
  'Общее':        { bg: '#F8FAFC', border: '#E2E8F0', text: '#475569', dot: '#94A3B8' },
};

function ConfBadge({ confidence, found }) {
  if (!found) return (
    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626', fontFamily: MONO }}>
      ✗ не найдено
    </span>
  );
  const color = confidence > 60 ? { bg: '#F0FDF4', border: '#BBF7D0', text: '#065F46' }
    : confidence > 35 ? { bg: '#FFFBEB', border: '#FDE68A', text: '#92400E' }
    : { bg: '#FEF2F2', border: '#FECACA', text: '#DC2626' };
  return (
    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: color.bg, border: `1px solid ${color.border}`, color: color.text, fontFamily: MONO }}>
      ✓ {confidence}% уверен.
    </span>
  );
}

function SourceTag({ source }) {
  const cat = Object.keys(CAT_COLORS).find(k => source.includes(k)) || 'Общее';
  const c   = CAT_COLORS[cat];
  return (
    <span style={{
      fontSize: 11, padding: '2px 10px', borderRadius: 20,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
    }}>{source}</span>
  );
}

function ChatCard({ item, idx }) {
  const [open, setOpen] = useState(false);
  const fmtTs = (ts) => ts ? new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <div style={{
      background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14,
      overflow: 'hidden', transition: 'box-shadow .15s, border-color .15s',
    }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(37,99,235,0.08)'; e.currentTarget.style.borderColor = '#BFDBFE'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = '#E2E8F0'; }}
    >
      {/* Header */}
      <button onClick={() => setOpen(!open)} style={{
        width: '100%', padding: '14px 18px', display: 'flex', alignItems: 'center',
        gap: 12, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, flexShrink: 0,
          background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700, color: '#1D4ED8', fontFamily: MONO,
        }}>#{item.id}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 13.5, fontWeight: 600, color: '#0F172A',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{item.question}</div>
          <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>{fmtTs(item.ts)}</div>
        </div>
        <ConfBadge confidence={Math.round(item.confidence * 100)} found={item.found} />
        <span style={{ fontSize: 12, color: '#94A3B8', marginLeft: 8, flexShrink: 0 }}>{open ? '▲' : '▼'}</span>
      </button>

      {/* Expanded */}
      {open && (
        <div style={{ borderTop: '1px solid #F1F5F9', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* User message */}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <div style={{
              maxWidth: '78%', padding: '10px 14px', borderRadius: '14px 14px 4px 14px',
              background: '#EFF6FF', border: '1px solid #BFDBFE',
              fontSize: 13.5, color: '#1E40AF', lineHeight: 1.6,
            }}>{item.question}</div>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: '#1D4ED8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0 }}>ВЫ</div>
          </div>

          {/* AI answer */}
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: 'linear-gradient(135deg,#2563EB,#7C3AED)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0 }}>AI</div>
            <div style={{ maxWidth: '78%' }}>
              <div style={{
                padding: '10px 14px', borderRadius: '14px 14px 14px 4px',
                background: '#F8FAFC', border: `1px solid ${item.found ? '#E2E8F0' : '#FECACA'}`,
                fontSize: 13.5, color: '#374151', lineHeight: 1.65, whiteSpace: 'pre-wrap',
              }}>{item.answer}</div>
              {item.sources?.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                  {item.sources.map((s, i) => <SourceTag key={i} source={s} />)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChatHistoryPage() {
  const [history, setHistory]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [sessionId, setSessionId] = useState('default');
  const [search, setSearch]       = useState('');
  const [filter, setFilter]       = useState('all'); // all | found | not_found

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/kb/chat/history?session_id=${sessionId}&limit=200`);
      const d = await r.json();
      const items = (d.history || []).map(h => ({
        id: h.id, question: h.question, answer: h.answer,
        sources: h.sources, confidence: h.confidence, found: h.found, ts: h.created_at,
      }));
      setHistory(items);
    } catch {}
    setLoading(false);
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  const filtered = history.filter(h => {
    if (filter === 'found' && !h.found) return false;
    if (filter === 'not_found' && h.found) return false;
    if (search && !h.question.toLowerCase().includes(search.toLowerCase()) &&
        !h.answer.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const stats = {
    total: history.length,
    found: history.filter(h => h.found).length,
    avgConf: history.length ? Math.round(history.filter(h=>h.found).reduce((a,h)=>a+h.confidence,0)/Math.max(history.filter(h=>h.found).length,1)*100) : 0,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#F8FAFC' }}>
      {/* Header */}
      <div style={{ padding: '20px 28px 0', background: '#fff', borderBottom: '1px solid #E2E8F0' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>💬 История чатов</div>
            <div style={{ fontSize: 13, color: '#94A3B8', marginTop: 2 }}>PostgreSQL · все сессии · чат-ассистент</div>
          </div>
          <button onClick={load} style={{
            padding: '8px 16px', borderRadius: 9, border: '1px solid #E2E8F0',
            background: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', color: '#475569',
          }}>↻ Обновить</button>
        </div>

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          {[
            { l: 'Всего диалогов',  v: stats.total,                  c: '#2563EB', bg: '#EFF6FF' },
            { l: 'Найдено ответов', v: stats.found,                  c: '#059669', bg: '#F0FDF4' },
            { l: 'Не найдено',      v: stats.total - stats.found,    c: '#DC2626', bg: '#FEF2F2' },
            { l: 'Ср. уверенность', v: `${stats.avgConf}%`,          c: '#7C3AED', bg: '#F5F3FF' },
          ].map(s => (
            <div key={s.l} style={{ padding: '10px 16px', borderRadius: 10, background: s.bg, border: `1px solid ${s.c}22` }}>
              <div style={{ fontSize: 10, color: s.c, fontWeight: 600, marginBottom: 3, letterSpacing: '0.04em' }}>{s.l.toUpperCase()}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: s.c, fontFamily: MONO }}>{s.v}</div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', paddingBottom: 14 }}>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="🔍 Поиск по вопросам и ответам..."
            style={{
              flex: 1, padding: '9px 14px', fontSize: 13, borderRadius: 9,
              border: '1px solid #E2E8F0', background: '#F8FAFC', outline: 'none', color: '#0F172A',
            }}
          />
          <div style={{ display: 'flex', gap: 4 }}>
            {[['all','Все'],['found','Найдено'],['not_found','Не найдено']].map(([v,l]) => (
              <button key={v} onClick={() => setFilter(v)} style={{
                padding: '7px 14px', borderRadius: 8, border: `1px solid ${filter===v?'#BFDBFE':'#E2E8F0'}`,
                background: filter === v ? '#EFF6FF' : '#fff',
                color: filter === v ? '#1D4ED8' : '#475569',
                fontSize: 12, fontWeight: 600, cursor: 'pointer',
              }}>{l}</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontSize: 12, color: '#94A3B8' }}>Сессия:</label>
            <select value={sessionId} onChange={e => setSessionId(e.target.value)} style={{
              padding: '7px 10px', borderRadius: 8, border: '1px solid #E2E8F0',
              background: '#fff', fontSize: 12, color: '#374151', outline: 'none',
            }}>
              <option value="default">default</option>
              <option value="demo">demo</option>
              <option value="admin">admin</option>
            </select>
          </div>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>⏳</div>
            <div style={{ fontSize: 14 }}>Загрузка из PostgreSQL...</div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>💬</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#475569', marginBottom: 8 }}>
              {search ? 'Ничего не найдено' : 'История пуста'}
            </div>
            <div style={{ fontSize: 13 }}>{search ? 'Попробуйте другой запрос' : 'Задайте первый вопрос в чате'}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 4 }}>
              Показано: {filtered.length} из {history.length} диалогов
            </div>
            {filtered.slice().reverse().map((item, i) => (
              <ChatCard key={item.id} item={item} idx={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
