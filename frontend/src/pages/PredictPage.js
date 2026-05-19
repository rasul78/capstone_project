import React, { useState, useRef, useCallback } from 'react';

const API   = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const TEAL  = '#0D9488';
const DARK  = '#0F172A';
const MUTED = '#64748B';
const BORDER= '#E2E8F0';
const MONO  = 'monospace';

/* ── Icons ─────────────────────────────────────────────────── */
const P = {
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  brain:  "M9 3a6 6 0 0 1 6 6c0 .91-.22 1.77-.62 2.52A6 6 0 0 1 9 21a6 6 0 0 1-5.9-7.1A6 6 0 0 1 9 3zm6 0a6 6 0 0 1 0 12",
  check:  "M20 6 9 17l-5-5",
  x:      "M18 6 6 18M6 6l12 12",
  eye:    "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  add:    "M12 5v14M5 12h14",
  info:   "M12 16v-4M12 8h.01M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0z",
  scan:   "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10",
  copy:   "M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2M16 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-2",
  edit:   "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
};
const Icon = ({ n, size = 18, color = 'currentColor', style = {} }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={color} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
    style={{ flexShrink: 0, display: 'block', ...style }}>
    <path d={P[n] || ''} />
  </svg>
);

function Dots({ color = TEAL }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block', animation: `dotB 1.2s ease ${i * 0.2}s infinite` }} />
      ))}
    </div>
  );
}

/* ── OCR→KB Modal ───────────────────────────────────────────── */
function OcrModal({ ocrData, filename, onConfirm, onCancel }) {
  const [name, setName]       = useState(filename.replace(/\.[^.]+$/, ''));
  const [cat, setCat]         = useState('Загружено');
  const [content, setContent] = useState(ocrData.text);

  const inp = {
    width: '100%', padding: '11px 14px', fontSize: 13.5, borderRadius: 10,
    outline: 'none', border: `1.5px solid ${BORDER}`, background: '#FAFAFA',
    color: DARK, fontFamily: 'inherit', boxSizing: 'border-box', transition: 'border-color .18s',
  };
  const fo = e => { e.target.style.borderColor = TEAL; e.target.style.background = '#fff'; };
  const bl = e => { e.target.style.borderColor = BORDER; e.target.style.background = '#FAFAFA'; };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 20, padding: '32px 36px', width: '100%', maxWidth: 600, boxShadow: '0 20px 60px rgba(0,0,0,0.15)', border: `1px solid ${BORDER}`, fontFamily: "'Inter',system-ui,sans-serif", maxHeight: '90vh', display: 'flex', flexDirection: 'column', gap: 0 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: DARK, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon n="brain" size={20} color={TEAL} />
            Добавить в базу знаний
          </div>
          <button onClick={onCancel} style={{ background: 'none', border: 'none', cursor: 'pointer', color: MUTED, display: 'flex', padding: 4, borderRadius: 6 }}>
            <Icon n="x" size={18} />
          </button>
        </div>

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          {[['Символов', ocrData.chars], ['Слов', ocrData.words], ['Строк', ocrData.lines]].map(([l, v]) => (
            <div key={l} style={{ padding: '6px 14px', borderRadius: 8, background: '#F0FDFA', border: '1px solid #99F6E4', fontSize: 12, color: '#0F766E' }}>
              <span style={{ fontWeight: 700, fontFamily: MONO }}>{v}</span> <span style={{ opacity: .7 }}>{l}</span>
            </div>
          ))}
        </div>

        {/* Fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto', flex: 1 }}>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.06em', marginBottom: 6 }}>НАЗВАНИЕ ДОКУМЕНТА *</div>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Введите название..." style={inp} onFocus={fo} onBlur={bl} />
          </div>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.06em', marginBottom: 6 }}>КАТЕГОРИЯ</div>
            <select value={cat} onChange={e => setCat(e.target.value)} style={{ ...inp, width: 'auto', minWidth: 200 }}
              onFocus={fo} onBlur={bl}>
              {['Загружено', 'Безопасность', 'HR', 'Финансы', 'IT', 'Этика', 'Общее'].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: MUTED, letterSpacing: '0.06em', marginBottom: 6 }}>
              РАСПОЗНАННЫЙ ТЕКСТ — отредактируйте при необходимости
            </div>
            <textarea value={content} onChange={e => setContent(e.target.value)} rows={12}
              style={{ ...inp, resize: 'vertical', lineHeight: 1.7, fontSize: 12.5, fontFamily: MONO }}
              onFocus={fo} onBlur={bl} />
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{ padding: '11px 22px', borderRadius: 10, border: `1px solid ${BORDER}`, background: '#fff', color: MUTED, fontSize: 13.5, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            Отмена
          </button>
          <button onClick={() => onConfirm(name, content, cat)} disabled={!name.trim() || !content.trim()} style={{
            padding: '11px 26px', borderRadius: 10, border: 'none', fontSize: 13.5, fontWeight: 600,
            cursor: name.trim() && content.trim() ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
            background: name.trim() && content.trim() ? `linear-gradient(135deg,${TEAL},#0891B2)` : '#E2E8F0',
            color: name.trim() && content.trim() ? '#fff' : '#94A3B8',
            boxShadow: name.trim() && content.trim() ? '0 4px 14px rgba(13,148,136,0.28)' : 'none',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <Icon n="brain" size={15} color={name.trim() && content.trim() ? '#fff' : '#94A3B8'} />
            Добавить в базу знаний
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main Page ──────────────────────────────────────────────── */
export default function PredictPage() {
  const [drag, setDrag]         = useState(false);
  const [preview, setPreview]   = useState(null);
  const [file, setFile]         = useState(null);
  const [ocrData, setOcrData]   = useState(null);
  const [ocrState, setOcrState] = useState('idle'); // idle|loading|done|empty|error
  const [showModal, setShowModal] = useState(false);
  const [kbAdded, setKbAdded]   = useState(false);
  const [toast, setToast]       = useState('');
  const [copied, setCopied]     = useState(false);
  const fileRef = useRef(null);

  const showToast = msg => { setToast(msg); setTimeout(() => setToast(''), 3500); };

  const runOcr = useCallback(async f => {
    setOcrState('loading'); setOcrData(null);
    try {
      const form = new FormData(); form.append('file', f);
      const r    = await fetch(`${API}/api/predict/ocr`, { method: 'POST', body: form });
      if (!r.ok) throw new Error('failed');
      const d = await r.json();
      setOcrData(d);
      setOcrState(d.chars > 0 ? 'done' : 'empty');
    } catch {
      setOcrState('error');
      setOcrData({ text: '', chars: 0, words: 0, lines: 0 });
    }
  }, []);

  const handleFile = useCallback(f => {
    if (!f?.type.startsWith('image/')) return;
    setFile(f); setPreview(URL.createObjectURL(f));
    setOcrData(null); setOcrState('idle'); setKbAdded(false); setCopied(false);
    runOcr(f);
  }, [runOcr]);

  const handleAddToKb = async (name, content, category) => {
    try {
      const r = await fetch(`${API}/api/kb/documents`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, content, category }),
      });
      if (!r.ok) throw new Error();
      setKbAdded(true); setShowModal(false);
      showToast(`✓ «${name}» добавлен в базу знаний`);
    } catch { showToast('Ошибка — проверьте подключение к бэкенду'); }
  };

  const handleCopy = () => {
    if (ocrData?.text) {
      navigator.clipboard.writeText(ocrData.text).then(() => {
        setCopied(true); setTimeout(() => setCopied(false), 2000);
      });
    }
  };

  const reset = () => {
    setPreview(null); setFile(null); setOcrData(null);
    setOcrState('idle'); setKbAdded(false); setCopied(false);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#F8FAFC', fontFamily: "'Inter',system-ui,sans-serif" }}>

      {/* ── Header ──────────────────────────────────────── */}
      <div style={{ padding: '18px 28px', background: '#fff', borderBottom: `1px solid ${BORDER}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, color: DARK, letterSpacing: '-0.03em', display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon n="scan" size={20} color={TEAL} /> OCR — Распознавание текста
          </div>
          <div style={{ fontSize: 13, color: MUTED, marginTop: 3 }}>
            Загрузите изображение или скан документа — текст будет извлечён и добавлен в базу знаний
          </div>
        </div>

        {ocrState === 'done' && ocrData?.chars > 0 && !kbAdded && (
          <button onClick={() => setShowModal(true)} style={{
            padding: '10px 20px', borderRadius: 10, border: 'none', fontSize: 13.5, fontWeight: 600,
            cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 8,
            background: `linear-gradient(135deg,${TEAL},#0891B2)`, color: '#fff',
            boxShadow: '0 4px 14px rgba(13,148,136,0.28)',
          }}>
            <Icon n="brain" size={15} color="#fff" /> Добавить в базу знаний
          </button>
        )}
        {kbAdded && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', background: '#F0FDFA', border: '1px solid #99F6E4', borderRadius: 10, color: '#0F766E', fontSize: 13.5, fontWeight: 600 }}>
            <Icon n="check" size={15} color="#0F766E" /> Добавлено в базу знаний
          </div>
        )}
      </div>

      {/* ── Body ────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '24px 28px', display: 'flex', gap: 22 }}>

        {/* Left — upload + preview */}
        <div style={{ width: '44%', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
            onClick={() => fileRef.current?.click()}
            style={{
              border: `2px dashed ${drag ? TEAL : '#CBD5E1'}`, borderRadius: 16, cursor: 'pointer',
              overflow: 'hidden', background: drag ? '#F0FDFA' : '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all .2s', minHeight: 260,
            }}
          >
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => handleFile(e.target.files[0])} />
            {preview
              ? <img src={preview} alt="preview" style={{ width: '100%', maxHeight: 420, objectFit: 'contain', display: 'block' }} />
              : (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <div style={{ width: 64, height: 64, borderRadius: 16, background: '#F0FDFA', border: `2px dashed ${TEAL}`, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                    <Icon n="upload" size={28} color={TEAL} />
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: DARK, marginBottom: 8 }}>Перетащи скан или фото</div>
                  <div style={{ fontSize: 12.5, color: MUTED, lineHeight: 1.6, marginBottom: 20 }}>
                    Поддерживаются документы, скриншоты,<br />фотографии с текстом
                  </div>
                  <div style={{ fontSize: 11, color: MUTED, fontFamily: MONO, marginBottom: 18 }}>JPG · PNG · WEBP · BMP · TIFF</div>
                  <div style={{ padding: '10px 22px', background: '#F0FDFA', border: `1.5px solid ${TEAL}`, borderRadius: 10, display: 'inline-block', fontSize: 13.5, color: TEAL, fontWeight: 600 }}>
                    или выбери файл
                  </div>
                </div>
              )
            }
          </div>

          {preview && (
            <button onClick={reset} style={{ padding: '9px', borderRadius: 9, border: `1px solid ${BORDER}`, background: '#fff', fontSize: 13, color: MUTED, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <Icon n="x" size={14} /> Загрузить другое изображение
            </button>
          )}

          {/* How-to hint */}
          {!preview && (
            <div style={{ padding: '16px 18px', background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: MUTED, letterSpacing: '0.06em', marginBottom: 10 }}>КАК ЭТО РАБОТАЕТ</div>
              {[
                ['1', 'Загрузи фото документа, скана или скриншота'],
                ['2', 'OCR автоматически извлечёт весь текст'],
                ['3', 'Укажи название и категорию'],
                ['4', 'Текст добавится в базу знаний для AI-ассистента'],
              ].map(([n, t]) => (
                <div key={n} style={{ display: 'flex', gap: 10, marginBottom: 8, alignItems: 'flex-start' }}>
                  <span style={{ width: 20, height: 20, borderRadius: '50%', background: TEAL, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1 }}>{n}</span>
                  <span style={{ fontSize: 12.5, color: MUTED, lineHeight: 1.5 }}>{t}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right — OCR result */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {ocrState === 'idle' && !preview && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 40, background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 16, textAlign: 'center' }}>
              <div style={{ width: 72, height: 72, borderRadius: 20, background: '#F0FDFA', border: '2px solid #99F6E4', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
                <Icon n="scan" size={34} color={TEAL} />
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: DARK, marginBottom: 10 }}>Результат появится здесь</div>
              <div style={{ fontSize: 13.5, color: MUTED, lineHeight: 1.7, maxWidth: 320 }}>
                После загрузки изображения OCR извлечёт текст — вы сможете отредактировать его и сохранить в базу знаний
              </div>
            </div>
          )}

          {/* OCR loading */}
          {ocrState === 'loading' && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 40, background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 16, textAlign: 'center' }}>
              <div style={{ marginBottom: 20 }}><Dots /></div>
              <div style={{ fontSize: 16, fontWeight: 600, color: DARK, marginBottom: 8 }}>Распознаю текст...</div>
              <div style={{ fontSize: 13, color: MUTED }}>EasyOCR / Tesseract анализирует изображение</div>
            </div>
          )}

          {/* OCR error */}
          {ocrState === 'error' && (
            <div style={{ background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 16, padding: '24px 26px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <Icon n="info" size={18} color="#DC2626" />
                <span style={{ fontSize: 15, fontWeight: 700, color: '#DC2626' }}>OCR недоступен</span>
              </div>
              <div style={{ fontSize: 13.5, color: MUTED, lineHeight: 1.8 }}>
                Установите одну из библиотек в окружении бэкенда:
              </div>
              <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  ['EasyOCR (рекомендуется)', 'pip install easyocr', '#F0FDFA', '#99F6E4', '#0F766E'],
                  ['Pytesseract', 'pip install pytesseract', '#EFF6FF', '#BFDBFE', '#1E40AF'],
                ].map(([label, cmd, bg, bd, tx]) => (
                  <div key={label} style={{ padding: '12px 16px', background: bg, border: `1px solid ${bd}`, borderRadius: 10 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: tx, marginBottom: 4 }}>{label}</div>
                    <code style={{ fontSize: 12.5, fontFamily: MONO, color: tx, background: 'transparent' }}>{cmd}</code>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* OCR empty */}
          {ocrState === 'empty' && (
            <div style={{ background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 16, padding: '32px 26px', textAlign: 'center' }}>
              <Icon n="eye" size={36} color="#CBD5E1" style={{ margin: '0 auto 16px' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: DARK, marginBottom: 8 }}>Текст не найден</div>
              <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.6 }}>
                На изображении нет читаемого текста, или качество слишком низкое.<br />
                Попробуйте более чёткое фото.
              </div>
            </div>
          )}

          {/* OCR done — show result */}
          {ocrState === 'done' && ocrData?.chars > 0 && (
            <>
              {/* Stats bar */}
              <div style={{ background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 14, padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon n="scan" size={16} color={TEAL} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#0F766E' }}>Текст распознан</span>
                  {ocrData.method && ocrData.method !== 'none' && (
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: '#F0FDFA', border: '1px solid #99F6E4', color: '#0F766E', fontFamily: MONO }}>
                      {ocrData.method}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {[['Символов', ocrData.chars], ['Слов', ocrData.words], ['Строк', ocrData.lines]].map(([l, v]) => (
                    <span key={l} style={{ fontSize: 12, padding: '3px 10px', borderRadius: 20, background: '#F0FDFA', border: '1px solid #99F6E4', color: '#0F766E', fontFamily: MONO }}>
                      <b>{v}</b> {l}
                    </span>
                  ))}
                </div>
              </div>

              {/* Text result */}
              <div style={{ background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 16, overflow: 'hidden', flex: 1, display: 'flex', flexDirection: 'column' }}>
                {/* Toolbar */}
                <div style={{ padding: '12px 18px', borderBottom: `1px solid #F1F5F9`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#F8FAFC' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: MUTED, letterSpacing: '0.06em' }}>РАСПОЗНАННЫЙ ТЕКСТ</span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={handleCopy} style={{ padding: '6px 12px', borderRadius: 7, border: `1px solid ${BORDER}`, background: copied ? '#F0FDFA' : '#fff', color: copied ? '#0F766E' : MUTED, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <Icon n={copied ? 'check' : 'copy'} size={13} color={copied ? '#0F766E' : MUTED} />
                      {copied ? 'Скопировано' : 'Копировать'}
                    </button>
                    {!kbAdded && (
                      <button onClick={() => setShowModal(true)} style={{ padding: '6px 14px', borderRadius: 7, border: `1.5px solid ${TEAL}`, background: '#F0FDFA', color: '#0F766E', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Icon n="add" size={13} color="#0F766E" /> В базу знаний
                      </button>
                    )}
                    {kbAdded && (
                      <span style={{ padding: '6px 12px', borderRadius: 7, background: '#F0FDFA', border: '1px solid #99F6E4', color: '#0F766E', fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Icon n="check" size={13} color="#0F766E" /> Сохранено
                      </span>
                    )}
                  </div>
                </div>

                {/* Text body */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px' }}>
                  <pre style={{ margin: 0, fontSize: 13.5, color: DARK, fontFamily: MONO, lineHeight: 1.8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {ocrData.text}
                  </pre>
                </div>
              </div>

              {/* CTA below text */}
              {!kbAdded && (
                <button onClick={() => setShowModal(true)} style={{
                  padding: '13px', borderRadius: 12, border: 'none', fontSize: 14, fontWeight: 600,
                  cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  background: `linear-gradient(135deg,${TEAL},#0891B2)`, color: '#fff',
                  boxShadow: '0 4px 16px rgba(13,148,136,0.30)',
                }}>
                  <Icon n="brain" size={16} color="#fff" />
                  Добавить распознанный текст в базу знаний ИИ-ассистента
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', bottom: 28, right: 28, padding: '13px 22px', background: DARK, color: '#fff', borderRadius: 12, fontSize: 13.5, fontWeight: 500, boxShadow: '0 8px 24px rgba(0,0,0,0.2)', zIndex: 999 }}>
          {toast}
        </div>
      )}

      {/* Modal */}
      {showModal && file && ocrData && (
        <OcrModal ocrData={ocrData} filename={file.name} onConfirm={handleAddToKb} onCancel={() => setShowModal(false)} />
      )}

      <style>{`@keyframes dotB{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}`}</style>
    </div>
  );
}