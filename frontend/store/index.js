import { create } from 'zustand';

const API = (process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/api';
const KB  = (process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/api/kb';
const AGT = (process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/api/agent';


export const useStore = create((set, get) => ({
  tab: 'docs',
  modelInfo: null,
  trainStatus: null,
  isTraining: false,
  prediction: null,
  predicting: false,
  notification: null,
  trainingConfig: { dataset: 'cifar10', epochs: 15, lr: 0.001, batch_size: 64 },
  kbDocs: [],
  kbStats: null,
  kbMessages: [],
  kbLoading: false,
  sessionId: localStorage.getItem('sentinel_session') || 'default',
  useAgentChat: true,

  setTab: (tab) => set({ tab }),
  setConfig: (cfg) => set((s) => ({ trainingConfig: { ...s.trainingConfig, ...cfg } })),
  setSessionId: (id) => { localStorage.setItem('sentinel_session', id); set({ sessionId: id }); },

  notify: (text, type = 'success') => {
    set({ notification: { text, type, id: Date.now() } });
    setTimeout(() => set({ notification: null }), 4000);
  },

  fetchModelInfo: async () => {
    try {
      const r = await fetch(`${API}/model/info`);
      set({ modelInfo: await r.json() });
    } catch {}
  },

  fetchStatus: async () => {
    try {
      const r = await fetch(`${API}/train/status`);
      const d = await r.json();
      set({ trainStatus: d, isTraining: d.is_training });
    } catch {}
  },

  startTraining: async () => {
    const { trainingConfig, notify } = get();
    try {
      const r = await fetch(`${API}/train/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trainingConfig),
      });
      if (r.ok) { set({ isTraining: true }); notify('Обучение запущено'); }
    } catch {
      notify('Запусти бэкенд: uvicorn main:app --reload', 'error');
    }
  },

  stopTraining: async () => {
    try { await fetch(`${API}/train/stop`, { method: 'POST' }); } catch {}
    set({ isTraining: false });
    get().notify('Обучение остановлено');
  },

  predictImage: async (file) => {
    set({ predicting: true, prediction: null });
    const form = new FormData();
    form.append('file', file);
    try {
      const r = await fetch(`${API}/predict`, { method: 'POST', body: form });
      set({ prediction: await r.json(), predicting: false });
    } catch {
      set({ predicting: false });
      get().notify('Ошибка предсказания', 'error');
    }
  },

  fetchKbDocs: async () => {
    try {
      const [dr, sr] = await Promise.all([
        fetch(`${KB}/documents`),
        fetch(`${KB}/stats`),
      ]);
      const dj = await dr.json();
      const sj = await sr.json();
      set({ kbDocs: dj.documents || [], kbStats: sj });
    } catch {}
  },

  addKbDoc: async (name, content, category) => {
    try {
      await fetch(`${KB}/documents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, content, category }),
      });
      get().fetchKbDocs();
      get().notify(`Документ «${name}» добавлен`);
      return true;
    } catch { return false; }
  },

  uploadKbFile: async (file) => {
    const form = new FormData();
    form.append('file', file);
    try {
      await fetch(`${KB}/documents/upload`, { method: 'POST', body: form });
      get().fetchKbDocs();
      get().notify(`Файл «${file.name}» загружен`);
      return true;
    } catch { return false; }
  },

  deleteKbDoc: async (id) => {
    try { await fetch(`${KB}/documents/${id}`, { method: 'DELETE' }); } catch {}
    get().fetchKbDocs();
  },

  sendKbChat: async (question) => {
    const { sessionId, useAgentChat } = get();
    const msg = { id: Date.now(), role: 'user', text: question };
    set((s) => ({ kbMessages: [...s.kbMessages, msg], kbLoading: true }));
    try {
      // v2: с кэшем, reranker'ом, httpx async и улучшенным промптом
      const endpoint = `${KB}/chat/fast/v2`;
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          session_id: sessionId,
          use_cache: true,
          rerank: true,
        }),
      });
      const d = await r.json();
      const confPct = d.found ? Math.round((d.confidence || 0) * (d.confidence > 1 ? 1 : 100)) : null;
      set((s) => ({
        kbMessages: [...s.kbMessages, {
          id: Date.now() + 1,
          role: 'assistant',
          text: d.answer,
          sources: d.sources || [],
          confidence: confPct,
          found: d.found,
          mode: d.mode,
          flags: d.flags || [],
        }],
        kbLoading: false,
      }));
    } catch {
      set((s) => ({
        kbMessages: [...s.kbMessages, {
          id: Date.now() + 1,
          role: 'assistant',
          text: 'Бэкенд недоступен. Запустите: cd backend && uvicorn main:app --reload',
          sources: [],
          found: false,
        }],
        kbLoading: false,
      }));
    }
  },
})); 