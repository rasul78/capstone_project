import React, { useEffect, useRef, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useStore } from '../store/index';
import PageHeader from '../components/PageHeader';

const MONO = "'JetBrains Mono', monospace";
const API  = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const TOOLTIP_STYLE = {
  backgroundColor: '#fff',
  border: '1px solid #E2E8F0',
  borderRadius: 10, fontSize: 11, fontFamily: MONO, color: '#0F172A',
  boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
};

function ConfigField({ label, field, type = 'number', options }) {
  const { trainingConfig, setConfig } = useStore();
  const val = trainingConfig[field];
  const common = {
    background: '#fff', border: '1px solid #E2E8F0',
    borderRadius: 10, padding: '9px 13px', color: '#0F172A', fontSize: 13,
    fontFamily: MONO, outline: 'none', width: '100%', transition: 'border-color .15s',
  };
  return (
    <div>
      <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 7 }}>
        {label.toUpperCase()}
      </div>
      {options ? (
        <select value={val} onChange={e => setConfig({ [field]: e.target.value })} style={common}>
          {options.map(o => <option key={o.v} value={o.v} style={{ background: '#fff', color: '#0F172A' }}>{o.l}</option>)}
        </select>
      ) : (
        <input type={type} value={val} step={field === 'lr' ? 0.0001 : 1}
          onChange={e => setConfig({ [field]: type === 'number' ? parseFloat(e.target.value) : e.target.value })}
          style={common}
          onFocus={e => { e.target.style.borderColor = 'rgba(99,102,241,0.5)'; }}
          onBlur={e =>  { e.target.style.borderColor = '#E2E8F0'; }} />
      )}
    </div>
  );
}

function StatCard({ label, value, color, sub }) {
  return (
    <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 14, padding: '16px 18px', borderBottom: `2px solid ${color}30` }}>
      <div style={{ fontSize: 24, fontWeight: 700, fontFamily: MONO, color, lineHeight: 1, marginBottom: 4 }}>{value}</div>
      <div style={{ fontSize: 11, color: '#94A3B8' }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: '#E2E8F0', marginTop: 2, fontFamily: MONO }}>{sub}</div>}
    </div>
  );
}

// ── История запусков из PostgreSQL ───────────────────
function TrainHistoryView() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/train/history`);
      const d = await r.json();
      setRuns(d.runs || []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const fmtTs = (ts) => ts ? new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
  const fmtDur = (start, end) => {
    if (!start || !end) return '—';
    const s = Math.round((new Date(end) - new Date(start)) / 1000);
    return s < 60 ? `${s}с` : `${Math.floor(s/60)}м ${s%60}с`;
  };

  const STATUS_COLOR = { running: '#fbbf24', finished: '#22d3a5', stopped: '#f87171' };

  // Build chart data from selected run's history
  const chartData = (() => {
    if (!selected?.history) return [];
    const h = typeof selected.history === 'string' ? JSON.parse(selected.history) : selected.history;
    return (h.train_loss || []).map((_, i) => ({
      epoch: i + 1,
      'Train loss': +((h.train_loss?.[i] || 0).toFixed(4)),
      'Val loss':   +((h.val_loss?.[i]   || 0).toFixed(4)),
      'Train acc':  +(((h.train_acc?.[i] || 0) * 100).toFixed(1)),
      'Val acc':    +(((h.val_acc?.[i]   || 0) * 100).toFixed(1)),
    }));
  })();

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <span style={{ fontSize: 11, color: '#94A3B8', fontFamily: MONO }}>🐘 PostgreSQL · training_runs</span>
        <button onClick={load} style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8, color: '#a78bfa', fontSize: 11, cursor: 'pointer', padding: '5px 12px' }}>↻ Обновить</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#94A3B8', fontSize: 12 }}>Загрузка из PostgreSQL...</div>
      ) : runs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', border: '1px solid #E2E8F0', borderRadius: 16, background: '#F8FAFC' }}>
          <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>⚡</div>
          <div style={{ fontSize: 14, color: '#94A3B8' }}>Нет запусков — начни обучение на вкладке «Обучение»</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1.6fr' : '1fr', gap: 16 }}>
          {/* Runs list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {runs.map(r => {
              const isSel = selected?.id === r.id;
              return (
                <div key={r.id} onClick={() => setSelected(isSel ? null : r)}
                  style={{
                    background: isSel ? 'rgba(99,102,241,0.12)' : '#F8FAFC',
                    border: `1px solid ${isSel ? 'rgba(99,102,241,0.3)' : '#F1F5F9'}`,
                    borderRadius: 12, padding: '14px 16px', cursor: 'pointer', transition: 'all .2s',
                  }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 10, fontFamily: MONO, color: '#94A3B8' }}>#{r.id}</span>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 20, fontFamily: MONO,
                        background: (STATUS_COLOR[r.status] || '#94a3b8') + '15',
                        color: STATUS_COLOR[r.status] || '#94a3b8',
                        border: `1px solid ${(STATUS_COLOR[r.status] || '#94a3b8')}30`,
                      }}>{r.status}</span>
                    </div>
                    <span style={{ fontSize: 10, color: '#CBD5E1', fontFamily: MONO }}>{fmtTs(r.started_at)}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    {[
                      ['dataset',  r.dataset?.toUpperCase()],
                      ['epochs',   r.epochs],
                      ['lr',       r.lr],
                      ['batch',    r.batch_size],
                      ['best acc', r.best_acc != null ? r.best_acc.toFixed(2) + '%' : '—'],
                      ['duration', fmtDur(r.started_at, r.finished_at)],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <div style={{ fontSize: 9, color: '#CBD5E1', fontFamily: MONO, letterSpacing: '0.08em' }}>{k.toUpperCase()}</div>
                        <div style={{ fontSize: 12, fontWeight: 600, fontFamily: MONO, color: k === 'best acc' ? '#22d3a5' : '#0F172A' }}>{v}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Run detail charts */}
          {selected && chartData.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 11, color: '#94A3B8', fontFamily: MONO }}>
                Графики запуска #{selected.id} · {selected.dataset?.toUpperCase()}
              </div>
              {[
                { title: 'Loss', keys: ['Train loss','Val loss'], colors: ['#818cf8','#f472b6'] },
                { title: 'Accuracy %', keys: ['Train acc','Val acc'], colors: ['#22d3a5','#fbbf24'], domain: [0,100] },
              ].map(chart => (
                <div key={chart.title} style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 14, padding: '14px 14px 8px' }}>
                  <div style={{ fontSize: 10, fontFamily: MONO, color: '#94A3B8', marginBottom: 10, letterSpacing: '0.06em' }}>{chart.title.toUpperCase()}</div>
                  <ResponsiveContainer width="100%" height={140}>
                    <LineChart data={chartData} margin={{ top: 2, right: 4, bottom: 0, left: -10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis dataKey="epoch" stroke="#E2E8F0" tick={{ fontSize: 10, fill: '#E2E8F0', fontFamily: MONO }} />
                      <YAxis domain={chart.domain} stroke="#E2E8F0" tick={{ fontSize: 10, fill: '#E2E8F0', fontFamily: MONO }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Legend wrapperStyle={{ fontSize: 10, fontFamily: MONO, color: '#94A3B8' }} />
                      {chart.keys.map((k, i) => (
                        <Line key={k} type="monotone" dataKey={k} stroke={chart.colors[i]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          )}
          {selected && chartData.length === 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F8FAFC', borderRadius: 14, border: '1px solid #E2E8F0' }}>
              <div style={{ textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>Нет данных графиков для этого запуска</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────
export default function TrainPage() {
  const { isTraining, trainStatus, trainingConfig, startTraining, stopTraining, fetchStatus } = useStore();
  const [view, setView]     = useState('train');
  const [liveLog, setLiveLog] = useState([]);
  const esRef  = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 2500);
    return () => clearInterval(t);
  }, [fetchStatus]);

  useEffect(() => {
    if (isTraining) {
      setLiveLog([]);
      esRef.current = new EventSource(`${API}/api/train/stream`);
      esRef.current.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          if (d.done) { esRef.current?.close(); return; }
          setLiveLog(prev => [...prev, d]);
        } catch {}
      };
      esRef.current.onerror = () => esRef.current?.close();
    }
    return () => esRef.current?.close();
  }, [isTraining]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: 99999, behavior: 'smooth' });
  }, [liveLog]);

  const hist     = trainStatus?.history || {};
  const baseData = (hist.train_loss || []).map((_, i) => ({
    epoch: i + 1,
    'Train loss': +((hist.train_loss?.[i] || 0).toFixed(4)),
    'Val loss':   +((hist.val_loss?.[i]   || 0).toFixed(4)),
    'Train acc':  +(((hist.train_acc?.[i] || 0) * 100).toFixed(1)),
    'Val acc':    +(((hist.val_acc?.[i]   || 0) * 100).toFixed(1)),
  }));
  const liveData  = liveLog.map(e => ({ epoch: e.epoch, 'Train loss': e.train_loss, 'Val loss': e.val_loss, 'Train acc': e.train_acc, 'Val acc': e.val_acc }));
  const chartData = liveData.length > 0 ? liveData : baseData;
  const last      = liveLog[liveLog.length - 1] || null;
  const bestAcc   = last?.best_val_acc || trainStatus?.best_val_acc || 0;
  const curEpoch  = last?.epoch || trainStatus?.epoch || '—';

  const tabBtn = (id) => ({
    padding: '7px 14px', borderRadius: 8, cursor: 'pointer',
    fontFamily: 'Manrope, sans-serif', fontWeight: 600, fontSize: 12, transition: 'all .15s',
    border: `1px solid ${view === id ? 'rgba(99,102,241,0.3)' : '#E2E8F0'}`,
    background: view === id ? 'rgba(99,102,241,0.2)' : '#F1F5F9',
    color: view === id ? '#a78bfa' : '#E2E8F0',
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <PageHeader icon="⚡" title="Обучение нейросети"
        subtitle="VisionNet CNN · PyTorch · CIFAR-10 / MNIST · история → PostgreSQL"
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {isTraining && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#22d3a5', boxShadow: '0 0 8px #22d3a5', animation: 'pulse 1s infinite', display: 'inline-block' }} />
                <span style={{ fontSize: 11, color: '#22d3a5', fontFamily: MONO }}>обучение...</span>
              </div>
            )}
            <button onClick={() => setView('train')} style={tabBtn('train')}>⚡ Обучение</button>
            <button onClick={() => setView('history')} style={tabBtn('history')}>🐘 История</button>
          </div>
        }
      />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

        {/* TRAIN VIEW */}
        {view === 'train' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Config */}
            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 16, padding: '20px 22px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr)) auto', gap: 14, alignItems: 'end' }}>
              <ConfigField label="Датасет" field="dataset" options={[{ v: 'cifar10', l: 'CIFAR-10' }, { v: 'mnist', l: 'MNIST' }]} />
              <ConfigField label="Эпохи"        field="epochs" />
              <ConfigField label="Learning Rate" field="lr" />
              <ConfigField label="Batch Size"    field="batch_size" />
              <button onClick={isTraining ? stopTraining : startTraining}
                style={{ padding: '10px 22px', borderRadius: 10, border: 'none', cursor: 'pointer', fontFamily: 'Manrope, sans-serif', fontWeight: 700, fontSize: 13, color: 'white', whiteSpace: 'nowrap', transition: 'all .2s', background: isTraining ? 'linear-gradient(135deg,#991b1b,#7f1d1d)' : 'linear-gradient(135deg,#4f46e5,#7c3aed)', boxShadow: isTraining ? '0 4px 12px rgba(153,27,27,0.4)' : '0 4px 16px rgba(79,70,229,0.4)' }}>
                {isTraining ? '⏹ Остановить' : '▶ Запустить'}
              </button>
            </div>

            {/* Live stats */}
            {(last || bestAcc > 0) && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
                <StatCard label="Эпоха"        value={last ? `${last.epoch}/${trainingConfig.epochs}` : curEpoch} color="#818cf8" />
                <StatCard label="Train loss"   value={last?.train_loss ?? '—'} color="#f472b6" />
                <StatCard label="Val accuracy" value={last ? last.val_acc + '%' : '—'} color="#22d3a5" />
                <StatCard label="Лучшая"       value={bestAcc + '%'} color="#fbbf24" sub="val accuracy" />
              </div>
            )}

            {/* Charts */}
            {chartData.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                {[
                  { title: 'Loss', keys: ['Train loss','Val loss'], colors: ['#818cf8','#f472b6'] },
                  { title: 'Accuracy %', keys: ['Train acc','Val acc'], colors: ['#22d3a5','#fbbf24'], domain: [0,100] },
                ].map(chart => (
                  <div key={chart.title} style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 16, padding: '16px 16px 8px' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', fontFamily: MONO, marginBottom: 12, letterSpacing: '0.06em' }}>{chart.title.toUpperCase()}</div>
                    <ResponsiveContainer width="100%" height={170}>
                      <LineChart data={chartData} margin={{ top: 2, right: 4, bottom: 0, left: -10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                        <XAxis dataKey="epoch" stroke="#E2E8F0" tick={{ fontSize: 10, fill: '#E2E8F0', fontFamily: MONO }} />
                        <YAxis domain={chart.domain} stroke="#E2E8F0" tick={{ fontSize: 10, fill: '#E2E8F0', fontFamily: MONO }} />
                        <Tooltip contentStyle={TOOLTIP_STYLE} />
                        <Legend wrapperStyle={{ fontSize: 10, fontFamily: MONO, color: '#94A3B8' }} />
                        {chart.keys.map((k, i) => (
                          <Line key={k} type="monotone" dataKey={k} stroke={chart.colors[i]} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: chart.colors[i] }} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ))}
              </div>
            )}

            {/* Log */}
            {liveLog.length > 0 && (
              <div style={{ background: 'rgba(6,8,14,0.9)', border: '1px solid #E2E8F0', borderRadius: 14, padding: 16 }}>
                <div style={{ fontSize: 10, color: '#94A3B8', fontFamily: MONO, letterSpacing: '0.1em', marginBottom: 10 }}>TRAINING LOG · сохраняется в PostgreSQL</div>
                <div ref={logRef} style={{ maxHeight: 180, overflowY: 'auto' }}>
                  {liveLog.slice(-20).map((e, i) => (
                    <div key={i} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr 1fr 1fr', gap: 16, padding: '4px 8px', borderRadius: 6, background: i === liveLog.slice(-20).length - 1 ? 'rgba(99,102,241,0.08)' : 'transparent', fontFamily: MONO, fontSize: 11 }}>
                      <span style={{ color: '#6366f1' }}>ep {String(e.epoch).padStart(3,'0')}</span>
                      <span style={{ color: '#94A3B8' }}>loss {e.train_loss}</span>
                      <span style={{ color: '#22d3a5' }}>val {e.val_acc}%</span>
                      <span style={{ color: '#fbbf24' }}>best {e.best_val_acc}%</span>
                      <span style={{ color: '#CBD5E1' }}>lr {e.lr}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* HISTORY VIEW */}
        {view === 'history' && <TrainHistoryView />}
      </div>

      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}`}</style>
    </div>
  );
}