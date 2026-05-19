import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../store/index';
import PageHeader from '../components/PageHeader';
import AgentProgress from '../components/AgentProgress';

const API  = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const MONO = "'JetBrains Mono', monospace";

const CAT_META = {
  'Безопасность': { color: '#5EEAD4', emoji: '🔒' },
  'HR':           { color: '#22d3a5', emoji: '👥' },
  'Финансы':      { color: '#fbbf24', emoji: '💰' },
  'Этика':        { color: '#f472b6', emoji: '⚖'  },
  'IT':           { color: '#60a5fa', emoji: '💻' },
  'Загружено':    { color: '#0D9488', emoji: '📤' },
  'Общее':        { color: '#94a3b8', emoji: '📄' },
};
const catMeta = (cat) => CAT_META[cat] || CAT_META['Общее'];

/* ─── Mini Markdown Renderer (без зависимостей) ────────────────── */
function MarkdownText({ text }) {
  if (!text) return null;

  // Разбиваем на блоки по двойному переводу строки
  const blocks = text.split(/\n\n+/);

  const renderInline = (s) => {
    // Защита от XSS — экранируем HTML
    let safe = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    // **жирный**
    safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // *курсив*
    safe = safe.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');
    // `код`
    safe = safe.replace(/`([^`]+?)`/g, '<code style="background:#F1F5F9;padding:2px 6px;border-radius:4px;font-family:JetBrains Mono,monospace;font-size:0.92em;color:#0F766E">$1</code>');
    // [ссылка](url)
    safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" style="color:#0D9488;text-decoration:underline">$1</a>');
    return <span dangerouslySetInnerHTML={{ __html: safe }} />;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {blocks.map((block, idx) => {
        const trimmed = block.trim();
        if (!trimmed) return null;

        // Заголовок ###
        if (trimmed.startsWith('### ')) {
          return <div key={idx} style={{ fontSize: 13.5, fontWeight: 700, color: '#0F172A', marginTop: 4 }}>
            {renderInline(trimmed.slice(4))}
          </div>;
        }
        if (trimmed.startsWith('## ')) {
          return <div key={idx} style={{ fontSize: 14.5, fontWeight: 700, color: '#0F172A', marginTop: 4 }}>
            {renderInline(trimmed.slice(3))}
          </div>;
        }

        // Горизонтальная линия
        if (/^---+$/.test(trimmed)) {
          return <hr key={idx} style={{ border: 'none', borderTop: '1px solid #E2E8F0', margin: '4px 0' }} />;
        }

        // Цитата > ...
        if (trimmed.startsWith('> ')) {
          return <div key={idx} style={{
            borderLeft: '3px solid #0D9488', paddingLeft: 12, color: '#475569',
            fontStyle: 'italic', background: '#F8FAFC', padding: '8px 12px', borderRadius: 6,
          }}>
            {renderInline(trimmed.slice(2))}
          </div>;
        }

        // Маркированный список — строки с • или - или *
        const lines = trimmed.split('\n');
        const isBullets = lines.every(l => /^\s*[•\-*]\s+/.test(l));
        if (isBullets && lines.length > 1) {
          return <ul key={idx} style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {lines.map((l, i) => <li key={i} style={{ lineHeight: 1.6 }}>
              {renderInline(l.replace(/^\s*[•\-*]\s+/, ''))}
            </li>)}
          </ul>;
        }

        // Нумерованный список
        const isNumbered = lines.every(l => /^\s*\d+\.\s+/.test(l));
        if (isNumbered && lines.length > 1) {
          return <ol key={idx} style={{ margin: 0, paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {lines.map((l, i) => <li key={i} style={{ lineHeight: 1.6 }}>
              {renderInline(l.replace(/^\s*\d+\.\s+/, ''))}
            </li>)}
          </ol>;
        }

        // Просто параграф (поддерживает single \n как <br>)
        return <div key={idx} style={{ lineHeight: 1.65 }}>
          {lines.map((line, i) => (
            <React.Fragment key={i}>
              {renderInline(line)}
              {i < lines.length - 1 && <br />}
            </React.Fragment>
          ))}
        </div>;
      })}
    </div>
  );
}

function Dots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '4px 2px' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 5, height: 5, borderRadius: '50%', background: '#0D9488',
          display: 'inline-block', animation: `dotBounce 1.2s ease ${i * 0.2}s infinite`,
        }} />
      ))}
    </div>
  );
}

function Message({ msg }) {
  const isUser    = msg.role === 'user';
  const conf      = msg.confidence;
  const confColor = conf > 60 ? '#0D9488' : conf > 35 ? '#D97706' : '#DC2626';

  return (
    <div style={{ display:'flex', gap:12, alignItems:'flex-start', flexDirection: isUser ? 'row-reverse' : 'row', animation:'msgIn .2s ease' }}>
      {/* Avatar */}
      <div style={{
        width:34, height:34, borderRadius:10, flexShrink:0,
        display:'flex', alignItems:'center', justifyContent:'center',
        fontSize:11, fontWeight:700, fontFamily:MONO,
        background: isUser ? '#E2E8F0' : 'linear-gradient(135deg,#0D9488,#0891B2)',
        color: isUser ? '#64748B' : 'white',
        border: isUser ? '1px solid #E2E8F0' : 'none',
        boxShadow: isUser ? 'none' : '0 4px 12px rgba(13,148,136,0.4)',
      }}>{isUser ? 'ВЫ' : 'AI'}</div>

      {/* Bubble */}
      <div style={{ maxWidth:'76%' }}>
        <div style={{
          padding:'11px 15px', fontSize:13.5, lineHeight:1.65, borderRadius:14,
          borderTopLeftRadius: isUser ? 14 : 3, borderTopRightRadius: isUser ? 3 : 14,
          background: isUser ? '#EFF6FF' : '#F8FAFC',
          color: isUser ? '#1E40AF' : '#1E293B',
          border: isUser ? '1px solid #BFDBFE' : '1px solid #E2E8F0',
          wordBreak:'break-word',
        }}>
          {msg.streaming && !msg.text && msg.statusText && (
            <span style={{ color:'#94A3B8', fontSize:13, fontStyle:'italic' }}>{msg.statusText}</span>
          )}
          {isUser ? (
            <div style={{ whiteSpace:'pre-wrap' }}>{msg.text}</div>
          ) : (
            <MarkdownText text={msg.text} />
          )}
          {msg.streaming && msg.text && (
            <span style={{ display:'inline-block', width:2, height:'1em', background:'#0D9488', marginLeft:2, verticalAlign:'text-bottom', animation:'blink .7s step-end infinite' }} />
          )}
        </div>

        {/* Badges + sources */}
        {!isUser && (msg.sources?.length > 0 || conf != null) && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:7, alignItems:'center' }}>

            {/* Mode badge */}
            {msg.mode && (
              <span style={{
                fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700,
                background: msg.mode==='rag' ? '#F0FDFA' : msg.mode==='web' ? '#EFF6FF' : '#F5F3FF',
                border: '1px solid ' + (msg.mode==='rag' ? '#99F6E4' : msg.mode==='web' ? '#BFDBFE' : '#DDD6FE'),
                color: msg.mode==='rag' ? '#0F766E' : msg.mode==='web' ? '#1D4ED8' : '#5B21B6',
              }}>
                {msg.mode==='rag' ? '⬡ RAG' : msg.mode==='web' ? '🌐 Web' : '⚡ Hybrid'}
              </span>
            )}

            {/* LLM badge */}
            {msg.flags && msg.found && (
              msg.flags.find(f => f.startsWith('groq')) ? (
                <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700, background:'#F0FDF4', border:'1px solid #86EFAC', color:'#15803D' }}>⚡ Groq</span>
              ) : msg.flags.find(f => f.startsWith('gemini')) ? (
                <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700, background:'#EFF6FF', border:'1px solid #BFDBFE', color:'#1D4ED8' }}>✦ Gemini</span>
              ) : msg.flags.includes('anthropic') ? (
                <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700, background:'#FFF7ED', border:'1px solid #FED7AA', color:'#C2410C' }}>✦ Claude</span>
              ) : msg.flags.find(f => f.startsWith('ollama:')) ? (
                <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700, background:'#F0FDF4', border:'1px solid #86EFAC', color:'#15803D' }}>
                  ⚙ {msg.flags.find(f => f.startsWith('ollama:')).replace('ollama:', '')}
                </span>
              ) : null
            )}

            {/* Confidence */}
            {conf != null && (
              <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontFamily:'monospace', fontWeight:700, background: conf>60?'#F0FDFA':conf>35?'#FFFBEB':'#FEF2F2', border:'1px solid '+(conf>60?'#99F6E4':conf>35?'#FDE68A':'#FECACA'), color:confColor }}>
                {conf}% уверен.
              </span>
            )}

            {/* Sources with relevance */}
            {msg.sources?.map((s, i) => {
              const det   = (msg.source_details || []).find(d => d.name === s);
              const score = det ? det.score : null;
              const m     = catMeta(Object.keys(CAT_META).find(k => s.includes(k)) || 'Общее');
              return (
                <span key={i} title={s} style={{
                  fontSize:10.5, padding:'3px 10px', borderRadius:20,
                  background: m.color + '14', border:'1px solid ' + m.color + '28',
                  color: m.color, fontFamily:MONO, fontWeight:500,
                  display:'inline-flex', alignItems:'center', gap:4, maxWidth:240,
                }}>
                  <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {'📄 ' + s}
                  </span>
                  {score !== null && (
                    <span style={{ opacity:0.7, fontSize:9.5, flexShrink:0 }}>{score + '%'}</span>
                  )}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── HistoryView ────────────────────────────────────────
function HistoryView({ sessionId }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/kb/chat/history?session_id=${sessionId}&limit=100`);
      const d = await r.json();
      setHistory(d.history || []);
    } catch {}
    setLoading(false);
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontSize: 13, color: '#94A3B8' }}>Загрузка истории...</div>
    </div>
  );

  if (!history.length) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 32, opacity: 0.3 }}>💬</div>
      <div style={{ fontSize: 13, color: '#94A3B8' }}>История пуста</div>
    </div>
  );

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {history.slice().reverse().map(h => (
        <div key={h.id} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '14px 18px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', marginBottom: 6 }}>{h.question}</div>
          <div style={{ fontSize: 12.5, color: '#374151', lineHeight: 1.6, marginBottom: 6 }}>{h.answer}</div>
          <div style={{ fontSize: 11, color: '#94A3B8', fontFamily: MONO }}>
            {h.created_at ? new Date(h.created_at).toLocaleString('ru-RU') : ''} · {Math.round((h.confidence||0)*100)}% уверен.
          </div>
        </div>
      ))}
    </div>
  );
}

// ── DocCard ─────────────────────────────────────────────
function DocCard({ doc, onDelete }) {
  const m = catMeta(doc.category || 'Общее');
  return (
    <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', lineHeight: 1.4, flex: 1 }}>{doc.name}</div>
        <button onClick={() => onDelete(doc.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#CBD5E1', fontSize: 16, padding: 2, flexShrink: 0 }}
          onMouseEnter={e => e.target.style.color='#EF4444'} onMouseLeave={e => e.target.style.color='#CBD5E1'}>×</button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10.5, padding: '2px 8px', borderRadius: 20, background: m.color + '14', border: `1px solid ${m.color}28`, color: m.color, fontFamily: MONO }}>
          {m.emoji} {doc.category || 'Общее'}
        </span>
        {doc.chunk_count > 0 && (
          <span style={{ fontSize: 10.5, padding: '2px 8px', borderRadius: 20, background: '#F8FAFC', border: '1px solid #E2E8F0', color: '#94A3B8', fontFamily: MONO }}>
            {doc.chunk_count} фрагм.
          </span>
        )}
        {doc.size > 0 && (
          <span style={{ fontSize: 10.5, padding: '2px 8px', borderRadius: 20, background: '#F8FAFC', border: '1px solid #E2E8F0', color: '#94A3B8', fontFamily: MONO }}>
            {(doc.size / 1024).toFixed(1)} KB
          </span>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────
export default function DocsChatPage() {
  const {
    kbDocs, kbStats, kbMessages, kbLoading,
    fetchKbDocs, addKbDoc, deleteKbDoc, sendKbChat, sessionId,
  } = useStore();

  const [view, setView]             = useState('chat');
  const [filterCat, setFilterCat]   = useState('Все');
  const [chatInput, setChatInput]   = useState('');
  const [addName, setAddName]       = useState('');
  const [addContent, setAddContent] = useState('');
  const [addCat, setAddCat]         = useState('Общее');
  const [addBusy, setAddBusy]       = useState(false);
  const [drag, setDrag]             = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  // v4.3 — Agentic streaming mode (Variant 9)
  const [showAgents, setShowAgents]     = useState(false);
  const [streamingQuery, setStreamingQuery] = useState(null);
  const [streamingAnswer, setStreamingAnswer] = useState(null);
  const bottomRef = useRef(null);
  const fileRef   = useRef(null);

  useEffect(() => { fetchKbDocs(); }, [fetchKbDocs]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [kbMessages, kbLoading]);

  const handleSend = useCallback((q) => {
    const text = (q || chatInput).trim();
    if (!text || kbLoading) return;
    setChatInput('');
    if (showAgents) {
      // Streaming mode — render AgentProgress + collect final answer
      setStreamingQuery(text);
      setStreamingAnswer(null);
    } else {
      sendKbChat(text);
    }
  }, [chatInput, kbLoading, sendKbChat, showAgents]);

  const handleStreamDone = useCallback((data) => {
    setStreamingAnswer(data);
    // Persist as a regular message after streaming finishes
    // (so chat history shows it in the normal list)
    setTimeout(() => {
      setStreamingQuery(null);
      setStreamingAnswer(null);
    }, 0);
    // Add to the store's message list via injected helper
    // (we reuse sendKbChat's bookkeeping pattern but synchronously)
    if (data && data.answer) {
      // Direct add — bypass network call
      useStore.setState(state => ({
        kbMessages: [
          ...state.kbMessages,
          { id: Date.now() - 1, role: 'user', text: streamingQuery },
          {
            id: Date.now(),
            role: 'assistant',
            text: data.answer,
            sources: data.sources,
            mode: data.mode,
            confidence: data.confidence,
            mcpTools: data.mcp_tools_used,
            provider: data.provider,
            criticPassed: data.critic_passed,
          },
        ],
      }));
    }
  }, [streamingQuery]);

  const handleAddDoc = async () => {
    if (!addName.trim() || !addContent.trim() || addBusy) return;
    setAddBusy(true);
    const ok = await addKbDoc(addName.trim(), addContent.trim(), addCat);
    setAddBusy(false);
    if (ok) { setAddName(''); setAddContent(''); setView('docs'); }
  };

  const [uploadStatus, setUploadStatus] = useState(null);   // {stage, message, error}

  const handleFile = (file) => {
    if (!file) return;
    // Show params modal before uploading
    setPendingFile(file);
    setUploadStatus(null);
  };

  const handleFileConfirm = async (name, category) => {
    if (!pendingFile) return;
    setAddBusy(true);
    setUploadStatus({ stage: 'sending', message: 'Отправляю файл на сервер...' });

    const form = new FormData();
    form.append('file', pendingFile);
    form.append('category', category);

    // Прогресс по времени (фейковый, но реалистичный для UX)
    let stageTimer1, stageTimer2, stageTimer3;
    stageTimer1 = setTimeout(() =>
      setUploadStatus({ stage: 'extract', message: 'Извлекаю текст из документа...' }), 1500);
    stageTimer2 = setTimeout(() =>
      setUploadStatus({ stage: 'embed', message: 'Создаю векторные представления (embeddings)...' }), 6000);
    stageTimer3 = setTimeout(() =>
      setUploadStatus({ stage: 'save', message: 'Сохраняю в базу знаний...' }), 15000);

    try {
      const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      const ctrl = new AbortController();
      // Таймаут 3 минуты на крупные PDF
      const timeoutId = setTimeout(() => ctrl.abort(), 180000);

      const r = await fetch(
        `${API_URL}/api/kb/documents/upload?category=${encodeURIComponent(category)}`,
        { method: 'POST', body: form, signal: ctrl.signal }
      );
      clearTimeout(timeoutId);

      [stageTimer1, stageTimer2, stageTimer3].forEach(clearTimeout);

      if (!r.ok) {
        const errText = await r.text().catch(() => '');
        let errMsg = `Ошибка сервера (HTTP ${r.status})`;
        try {
          const errJson = JSON.parse(errText);
          errMsg = errJson.detail || errMsg;
        } catch {}
        setUploadStatus({ stage: 'error', error: errMsg });
        setAddBusy(false);
        return;
      }

      const data = await r.json();
      setUploadStatus({
        stage: 'success',
        message: `✅ Загружено: ${data.chunks || 0} фрагментов, ${(data.size/1024).toFixed(1)} KB`,
      });

      // Обновляем список и закрываем модалку через 1.5 сек
      fetchKbDocs();
      setTimeout(() => {
        setPendingFile(null);
        setUploadStatus(null);
        setAddBusy(false);
        setView('docs');
      }, 1500);

    } catch (err) {
      [stageTimer1, stageTimer2, stageTimer3].forEach(clearTimeout);
      const errMsg = err.name === 'AbortError'
        ? 'Превышено время ожидания (3 минуты). Файл слишком большой или сервер занят.'
        : `Ошибка: ${err.message || 'не удалось подключиться к серверу'}`;
      setUploadStatus({ stage: 'error', error: errMsg });
      setAddBusy(false);
    }
  };

  const cats  = ['Все', ...new Set(kbDocs.map(d => d.category))];
  const shown = filterCat === 'Все' ? kbDocs : kbDocs.filter(d => d.category === filterCat);

  const SUGGESTIONS = [
    'Как оформить заявку на отпуск?',
    'Что делать при инциденте безопасности?',
    'Какой лимит корпоративной карты?',
    'Правила дресс-кода в офисе?',
  ];

  const inputSt = {
    background: '#fff', border: '1px solid #E2E8F0',
    borderRadius: 10, padding: '10px 13px', color: '#0F172A', fontSize: 13,
    fontFamily: 'Manrope, sans-serif', outline: 'none', width: '100%', transition: 'border-color .15s',
  };

  const tabBtn = (id) => ({
    padding: '7px 13px', borderRadius: 8, cursor: 'pointer',
    fontFamily: 'Manrope, sans-serif', fontWeight: 600, fontSize: 12, transition: 'all .15s',
    border: `1px solid ${view === id ? '#0D9488' : '#E2E8F0'}`,
    background: view === id ? '#F0FDFA' : '#F1F5F9',
    color: view === id ? '#0D9488' : '#64748B',
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#F8FAFC' }}>
      <PageHeader
        icon="◈" title="🧠 База знаний"
        subtitle={kbStats ? `${kbStats.total_docs} документов · ${kbStats.total_chunks} фрагментов · PostgreSQL` : 'RAG · MiniTransformer · PostgreSQL'}
        right={
          <div style={{ display: 'flex', gap: 5 }}>
            {[
              { id: 'chat',    label: '💬 Чат'       },
              { id: 'history', label: '🐘 История'   },
              { id: 'docs',    label: '📚 Документы' },
              { id: 'add',     label: '＋ Добавить'  },
            ].map(t => <button key={t.id} onClick={() => setView(t.id)} style={tabBtn(t.id)}>{t.label}</button>)}
          </div>
        }
      />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>

        {/* CHAT */}
        {view === 'chat' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              {kbMessages.length === 0 ? (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center' }}>
                  <div style={{ width: 72, height: 72, borderRadius: 20, marginBottom: 20, background: 'linear-gradient(135deg,rgba(79,70,229,0.25),rgba(8,145,178,0.2))', border: '1px solid rgba(13,148,136,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 32, boxShadow: '0 0 40px rgba(13,148,136,0.12)' }}>🤖</div>
                  <h2 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: '#0F172A', marginBottom: 8 }}>Спроси нейросеть</h2>
                  <p style={{ fontSize: 13, color: '#94A3B8', maxWidth: 360, lineHeight: 1.65, marginBottom: 28 }}>Задай вопрос — система найдёт ответ в загруженных документах. Все диалоги сохраняются в PostgreSQL.</p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, width: '100%', maxWidth: 480 }}>
                    {SUGGESTIONS.map(q => (
                      <button key={q} onClick={() => handleSend(q)} style={{ padding: '11px 14px', background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 12, color: '#64748B', fontSize: 12, cursor: 'pointer', fontFamily: 'Manrope, sans-serif', textAlign: 'left', lineHeight: 1.4, transition: 'all .15s' }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = '#0D9488'; e.currentTarget.style.color = '#0F172A'; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = '#E2E8F0'; e.currentTarget.style.color = '#64748B'; }}
                      >{q}</button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {kbMessages.map(m => <Message key={m.id} msg={m} />)}
                  {/* v4.3: Agentic streaming pipeline visualization */}
                  {showAgents && streamingQuery && (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                      <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, background: 'linear-gradient(135deg,#0D9488,#0891B2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'white', fontWeight: 700, fontFamily: MONO, boxShadow: '0 4px 12px rgba(13,148,136,0.4)' }}>AI</div>
                      <div style={{ flex: 1, maxWidth: 720 }}>
                        <AgentProgress
                          question={streamingQuery}
                          sessionId={sessionId}
                          useWeb={true}
                          useMcp={true}
                          onDone={handleStreamDone}
                          onError={(msg) => {
                            setStreamingAnswer({ answer: '⚠️ ' + msg, sources: [] });
                          }}
                        />
                      </div>
                    </div>
                  )}
                  {kbLoading && !showAgents && (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                      <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, background: 'linear-gradient(135deg,#0D9488,#0891B2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'white', fontWeight: 700, fontFamily: MONO, boxShadow: '0 4px 12px rgba(13,148,136,0.4)' }}>AI</div>
                      <div style={{ padding: '10px 14px', background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, borderTopLeftRadius: 3 }}><Dots /></div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </>
              )}
            </div>
            {/* Input */}
            <div style={{ padding: '14px 24px 18px', borderTop: '1px solid #E2E8F0', background: '#fff' }}>
              {/* v4.3 — Agentic mode toggle */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                <button
                  onClick={() => setShowAgents(!showAgents)}
                  style={{
                    fontSize: 11, padding: '4px 10px', borderRadius: 6,
                    border: '1px solid ' + (showAgents ? '#0D9488' : '#E2E8F0'),
                    background: showAgents ? '#ECFEFF' : '#fff',
                    color: showAgents ? '#0D9488' : '#64748B',
                    cursor: 'pointer', fontFamily: 'Manrope, sans-serif',
                    fontWeight: 600,
                  }}>
                  {showAgents ? '🔬 Agentic mode ON' : '🔬 Show agent pipeline'}
                </button>
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, padding: '4px 4px 4px 16px' }}>
                <textarea value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  rows={1} placeholder="Задай вопрос о правилах, политиках или процедурах..."
                  style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#0F172A', fontSize: 13.5, fontFamily: 'Manrope, sans-serif', resize: 'none', padding: '8px 0', lineHeight: 1.5, maxHeight: 100 }} />
                <button onClick={() => handleSend()} disabled={!chatInput.trim() || kbLoading}
                  style={{ width: 40, height: 40, borderRadius: 10, border: 'none', flexShrink: 0, margin: 2, cursor: chatInput.trim() && !kbLoading ? 'pointer' : 'not-allowed', background: chatInput.trim() && !kbLoading ? 'linear-gradient(135deg,#0D9488,#0891B2)' : '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all .15s', boxShadow: chatInput.trim() && !kbLoading ? '0 4px 12px rgba(13,148,136,0.3)' : 'none' }}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10M8 3l5 5-5 5" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              </div>
              <div style={{ textAlign: 'center', marginTop: 8, fontSize: 10.5, color: '#CBD5E1', fontFamily: MONO }}>
                Enter — отправить · Shift+Enter — перенос · {kbStats?.total_chunks || 0} фрагментов в индексе · История → PostgreSQL
              </div>
            </div>
          </div>
        )}

        {/* HISTORY */}
        {view === 'history' && <HistoryView sessionId={sessionId} />}

        {/* DOCS */}
        {view === 'docs' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 20 }}>
              {[
                { l: 'ДОКУМЕНТОВ',  v: kbStats?.total_docs || 0,  c: '#0D9488' },
                { l: 'ФРАГМЕНТОВ', v: kbStats?.total_chunks || 0, c: '#22d3a5' },
                { l: 'СЛОВАРЬ',    v: kbStats?.vocab_size?.toLocaleString() || '—', c: '#fbbf24' },
                { l: 'ПАРАМЕТРЫ',  v: kbStats ? (kbStats.encoder_params / 1e6).toFixed(2) + 'M' : '—', c: '#f472b6' },
              ].map(s => (
                <div key={s.l} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, padding: '14px 16px' }}>
                  <div style={{ fontSize: 9, color: '#94A3B8', letterSpacing: '0.1em', fontFamily: MONO, marginBottom: 6 }}>{s.l}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: MONO, color: s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
              {cats.map(cat => {
                const active = filterCat === cat;
                const m = catMeta(cat);
                const cnt = cat === 'Все' ? kbDocs.length : kbDocs.filter(d => d.category === cat).length;
                return (
                  <button key={cat} onClick={() => setFilterCat(cat)} style={{ padding: '5px 12px', borderRadius: 20, cursor: 'pointer', background: active ? m.color + '18' : '#F8FAFC', color: active ? m.color : '#64748B', border: `1px solid ${active ? m.color + '35' : '#F1F5F9'}`, fontSize: 11, fontFamily: 'Manrope, sans-serif', fontWeight: 600, transition: 'all .15s' }}>
                    {cat === 'Все' ? `Все (${cnt})` : `${m.emoji} ${cat} (${cnt})`}
                  </button>
                );
              })}
            </div>
            {shown.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>📭</div>
                <div style={{ fontSize: 14, color: '#94A3B8' }}>Нет документов</div>
                <button onClick={() => setView('add')} style={{ marginTop: 16, padding: '9px 20px', background: 'rgba(13,148,136,0.15)', border: '1px solid rgba(13,148,136,0.25)', borderRadius: 10, color: '#0D9488', fontSize: 12, cursor: 'pointer', fontFamily: 'Manrope, sans-serif', fontWeight: 600 }}>+ Добавить документ</button>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(270px,1fr))', gap: 10 }}>
                {shown.map(d => <DocCard key={d.id} doc={d} onDelete={deleteKbDoc} />)}
              </div>
            )}
          </div>
        )}

        {/* ADD */}
        {view === 'add' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '28px' }}>
            <div style={{ maxWidth: 680, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                onDrop={e => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
                onClick={() => fileRef.current?.click()}
                style={{ border: `2px dashed ${drag ? 'rgba(13,148,136,0.6)' : '#E2E8F0'}`, borderRadius: 16, padding: '36px 20px', textAlign: 'center', cursor: 'pointer', background: drag ? 'rgba(13,148,136,0.06)' : '#F8FAFC', transition: 'all .2s' }}>
                <input ref={fileRef} type="file" accept=".txt,.md,.csv,.json,.pdf" style={{ display: 'none' }} onChange={e => handleFile(e.target.files[0])} />
                {addBusy ? (
                  <div style={{ color: '#0D9488', fontSize: 13 }}><Dots /><div style={{ marginTop: 8 }}>Векторизация и сохранение в PostgreSQL...</div></div>
                ) : (
                  <>
                    <div style={{ fontSize: 36, marginBottom: 12, opacity: drag ? 0.8 : 0.4 }}>📁</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#64748B' }}>Перетащи файл или кликни</div>
                    <div style={{ fontSize: 11, color: '#CBD5E1', marginTop: 6, fontFamily: MONO }}>.txt · .md · .csv · .json</div>
                  </>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, color: '#CBD5E1', fontSize: 11 }}>
                <div style={{ flex: 1, height: 1, background: '#F1F5F9' }} />или введи текст вручную
                <div style={{ flex: 1, height: 1, background: '#F1F5F9' }} />
              </div>
              <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 16, padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 11, color: '#94A3B8', display: 'block', marginBottom: 7, fontFamily: MONO, letterSpacing: '0.05em' }}>НАЗВАНИЕ *</label>
                    <input value={addName} onChange={e => setAddName(e.target.value)} placeholder="Политика безопасности v2.1..." style={inputSt}
                      onFocus={e => { e.target.style.borderColor = 'rgba(13,148,136,0.4)'; }} onBlur={e => { e.target.style.borderColor = '#E2E8F0'; }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: '#94A3B8', display: 'block', marginBottom: 7, fontFamily: MONO, letterSpacing: '0.05em' }}>КАТЕГОРИЯ</label>
                    <select value={addCat} onChange={e => setAddCat(e.target.value)} style={{ ...inputSt, width: 'auto', paddingRight: 24 }}>
                      {['Безопасность','HR','Финансы','IT','Этика','Общее'].map(c => <option key={c} value={c} style={{ background: '#fff' }}>{c}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: 11, color: '#94A3B8', display: 'block', marginBottom: 7, fontFamily: MONO, letterSpacing: '0.05em' }}>СОДЕРЖИМОЕ *</label>
                  <textarea value={addContent} onChange={e => setAddContent(e.target.value)} rows={10} placeholder="Вставь текст политики, регламента или инструкции..."
                    style={{ ...inputSt, resize: 'vertical', lineHeight: 1.65 }}
                    onFocus={e => { e.target.style.borderColor = 'rgba(13,148,136,0.4)'; }} onBlur={e => { e.target.style.borderColor = '#E2E8F0'; }} />
                  <div style={{ fontSize: 10, color: '#CBD5E1', marginTop: 5, fontFamily: MONO, textAlign: 'right' }}>{addContent.split(/\s+/).filter(Boolean).length} слов</div>
                </div>
                <button onClick={handleAddDoc} disabled={!addName.trim() || !addContent.trim() || addBusy}
                  style={{ padding: '13px', borderRadius: 12, border: 'none', cursor: 'pointer', fontFamily: 'Manrope, sans-serif', fontWeight: 700, fontSize: 14, transition: 'all .2s', background: addName.trim() && addContent.trim() && !addBusy ? 'linear-gradient(135deg,#0D9488,#0891B2)' : '#F1F5F9', color: addName.trim() && addContent.trim() && !addBusy ? 'white' : '#94A3B8', boxShadow: addName.trim() && addContent.trim() && !addBusy ? '0 8px 24px rgba(13,148,136,0.25)' : 'none' }}>
                  {addBusy ? '⏳ Сохранение в PostgreSQL...' : '🧠 Добавить в базу знаний'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>


      {/* File params modal */}
      {pendingFile && (
        <div style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.40)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:1000, padding:20 }}>
          <div style={{ background:'#fff', borderRadius:20, padding:'32px 36px', width:'100%', maxWidth:460, boxShadow:'0 20px 60px rgba(0,0,0,0.15)', border:'1px solid #E2E8F0', fontFamily:"'Inter',system-ui,sans-serif" }}>
            <div style={{ fontSize:17, fontWeight:700, color:'#0F172A', marginBottom:6 }}>📄 Параметры документа</div>
            <div style={{ fontSize:13, color:'#64748B', marginBottom:20 }}>{pendingFile.name} · {(pendingFile.size/1024).toFixed(1)} KB</div>
            <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <div>
                <div style={{ fontSize:11.5, fontWeight:700, color:'#64748B', letterSpacing:'0.06em', marginBottom:6 }}>НАЗВАНИЕ ДОКУМЕНТА *</div>
                <input
                  id="modal-doc-name"
                  defaultValue={pendingFile.name.replace(/\.[^.]+$/, '')}
                  disabled={addBusy}
                  style={{ width:'100%', padding:'11px 14px', fontSize:13.5, borderRadius:9, border:'1.5px solid #E2E8F0', background: addBusy ? '#F1F5F9' : '#FAFAFA', color:'#0F172A', fontFamily:'inherit', boxSizing:'border-box', outline:'none', opacity: addBusy ? 0.6 : 1 }}
                  onFocus={e => e.target.style.borderColor='#0D9488'} onBlur={e => e.target.style.borderColor='#E2E8F0'} />
              </div>
              <div>
                <div style={{ fontSize:11.5, fontWeight:700, color:'#64748B', letterSpacing:'0.06em', marginBottom:6 }}>КАТЕГОРИЯ</div>
                <select id="modal-doc-cat" defaultValue="Загружено" disabled={addBusy} style={{ padding:'11px 14px', fontSize:13.5, borderRadius:9, border:'1.5px solid #E2E8F0', background: addBusy ? '#F1F5F9' : '#FAFAFA', color:'#0F172A', fontFamily:'inherit', outline:'none', minWidth:200, opacity: addBusy ? 0.6 : 1 }}
                  onFocus={e => e.target.style.borderColor='#0D9488'} onBlur={e => e.target.style.borderColor='#E2E8F0'}>
                  {['Загружено','Безопасность','HR','Финансы','IT','Этика','Общее'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>

            {/* Индикатор прогресса / ошибки / успеха */}
            {uploadStatus && (
              <div style={{
                marginTop: 18,
                padding: '12px 14px',
                borderRadius: 10,
                fontSize: 13,
                fontFamily: 'inherit',
                background: uploadStatus.stage === 'error'   ? '#FEF2F2'
                          : uploadStatus.stage === 'success' ? '#F0FDF4'
                          : '#F0FDFA',
                border: '1px solid ' + (
                          uploadStatus.stage === 'error'   ? '#FECACA'
                        : uploadStatus.stage === 'success' ? '#BBF7D0'
                        : '#A7F3D0'),
                color:    uploadStatus.stage === 'error'   ? '#991B1B'
                        : uploadStatus.stage === 'success' ? '#166534'
                        : '#115E59',
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                {uploadStatus.stage !== 'success' && uploadStatus.stage !== 'error' && (
                  <div style={{
                    width: 16, height: 16, borderRadius: '50%',
                    border: '2px solid #A7F3D0', borderTopColor: '#0D9488',
                    animation: 'spin 0.8s linear infinite',
                    flexShrink: 0,
                  }} />
                )}
                <div style={{ flex: 1 }}>
                  {uploadStatus.error || uploadStatus.message}
                </div>
              </div>
            )}

            <div style={{ display:'flex', gap:10, marginTop:24, justifyContent:'flex-end' }}>
              <button
                disabled={addBusy}
                onClick={() => { setPendingFile(null); setUploadStatus(null); }}
                style={{ padding:'10px 20px', borderRadius:10, border:'1px solid #E2E8F0', background:'#fff', color:'#64748B', fontSize:13.5, fontWeight:600, cursor: addBusy ? 'not-allowed' : 'pointer', fontFamily:'inherit', opacity: addBusy ? 0.5 : 1 }}>
                Отмена
              </button>
              <button
                disabled={addBusy}
                onClick={() => {
                  if (addBusy) return;
                  const name = document.getElementById('modal-doc-name')?.value || pendingFile.name;
                  const cat  = document.getElementById('modal-doc-cat')?.value  || 'Загружено';
                  handleFileConfirm(name, cat);
                }}
                style={{
                  padding:'10px 24px', borderRadius:10, border:'none', fontSize:13.5, fontWeight:600,
                  cursor: addBusy ? 'not-allowed' : 'pointer', fontFamily:'inherit',
                  background: addBusy ? '#94A3B8' : 'linear-gradient(135deg,#0D9488,#0891B2)',
                  color:'#fff',
                  boxShadow: addBusy ? 'none' : '0 4px 14px rgba(13,148,136,0.28)',
                  display:'flex', alignItems:'center', gap:8,
                  minWidth: 180,
                  justifyContent: 'center',
                }}>
                {addBusy && (
                  <div style={{
                    width:14, height:14, borderRadius:'50%',
                    border:'2px solid rgba(255,255,255,0.4)',
                    borderTopColor:'#fff', animation:'spin 0.8s linear infinite',
                  }} />
                )}
                {addBusy ? 'Загрузка...' : 'Загрузить в базу знаний'}
              </button>
            </div>
          </div>
        </div>
      )}
      <style>{`
        @keyframes msgIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0}} @keyframes dotBounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}
        @keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
        textarea::placeholder,input::placeholder{color:#CBD5E1;}
        select option{background:#fff;color:#0F172A;}
      `}</style>
    </div>
  );
}