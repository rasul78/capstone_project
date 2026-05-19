// frontend/src/components/AgentProgress.js
// Streaming agentic progress visualization (Variant 9)
//
// Listens to /api/kb/chat/stream SSE events and renders a live timeline:
//
//   🧭 Planner       ─── ✓ 50ms  Will call: doc_search, legal, web
//   📂 DocSearch     ─── ✓ 200ms Found 5 chunks (HR_Vacation_Policy 87%)
//   ⚖️ Legal        ─── ✓ 150ms legal_rk.get_article
//   🌐 WebResearch   ─── ⏭ skipped
//   🧠 Synthesis     ─── ✓ 800ms groq:llama-3.3-70b
//   🔍 Critic        ─── ✓  30ms passed
//
// On 'done' event, the AI answer message is rendered below.

import React, { useEffect, useState, useRef } from 'react';

const STATUSES = {
  pending:  { color: '#94A3B8', icon: '○' },
  running:  { color: '#0D9488', icon: '◐' },
  done:     { color: '#16A34A', icon: '✓' },
  skipped:  { color: '#94A3B8', icon: '⏭' },
  error:    { color: '#DC2626', icon: '✗' },
};

export default function AgentProgress({ question, sessionId, useWeb, useMcp, onDone, onError }) {
  const [plan, setPlan]       = useState([]);    // list of agents from "plan" event
  const [steps, setSteps]     = useState({});    // {agent: {status, latency, summary}}
  const [error, setError]     = useState(null);
  const abortRef              = useRef(null);

  useEffect(() => {
    if (!question) return;

    abortRef.current = new AbortController();
    const run = async () => {
      try {
        const resp = await fetch('http://localhost:8000/api/kb/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question, session_id: sessionId || 'default',
            use_web: useWeb !== false, use_mcp: useMcp !== false,
            use_critic: true,
          }),
          signal: abortRef.current.signal,
        });

        if (!resp.ok || !resp.body) {
          throw new Error('Stream failed: HTTP ' + resp.status);
        }

        const reader  = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer    = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE events end with \n\n
          let idx;
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);

            let ev = 'message';
            let dataStr = '';
            raw.split('\n').forEach((line) => {
              if (line.startsWith('event: ')) ev = line.slice(7).trim();
              if (line.startsWith('data: '))  dataStr = line.slice(6);
            });
            if (!dataStr) continue;

            let data;
            try { data = JSON.parse(dataStr); } catch { continue; }

            if (ev === 'plan') {
              setPlan(data.agents);
              const init = {};
              data.agents.forEach(a => { init[a.name] = { status: 'pending' }; });
              setSteps(init);
            }
            else if (ev === 'agent_started') {
              setSteps(s => ({ ...s, [data.agent]: { ...s[data.agent], status: 'running' } }));
            }
            else if (ev === 'agent_finished') {
              setSteps(s => ({
                ...s,
                [data.agent]: {
                  status: data.skipped ? 'skipped' : 'done',
                  latency: data.latency_ms,
                  summary: _summarize(data),
                  raw: data,
                },
              }));
            }
            else if (ev === 'done') {
              if (onDone) onDone(data);
            }
            else if (ev === 'error') {
              setError(data.message);
              if (onError) onError(data.message);
            }
          }
        }
      } catch (e) {
        if (e.name !== 'AbortError') {
          setError(e.message);
          if (onError) onError(e.message);
        }
      }
    };
    run();

    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [question, sessionId, useWeb, useMcp]);

  if (error) {
    return (
      <div style={{ padding: 12, background: '#FEF2F2', border: '1px solid #FCA5A5',
                    borderRadius: 8, color: '#991B1B', fontSize: 13 }}>
        ⚠️ Streaming error: {error}
      </div>
    );
  }

  if (plan.length === 0) {
    return (
      <div style={{ padding: 14, color: '#64748B', fontSize: 13, fontStyle: 'italic' }}>
        🧭 Planning…
      </div>
    );
  }

  return (
    <div style={{
      background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 10,
      padding: '12px 14px', marginBottom: 8, fontFamily: 'system-ui',
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#64748B',
                    textTransform: 'uppercase', letterSpacing: 0.5,
                    marginBottom: 8 }}>
        Agentic Pipeline
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {plan.map((agent, i) => {
          const st = steps[agent.name] || { status: 'pending' };
          const meta = STATUSES[st.status] || STATUSES.pending;
          const isRunning = st.status === 'running';

          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '6px 10px', borderRadius: 6,
              background: isRunning ? '#ECFEFF' : 'transparent',
              border: isRunning ? '1px solid #67E8F9' : '1px solid transparent',
              transition: 'all 0.2s',
            }}>
              <span style={{
                fontSize: 16, color: meta.color, width: 18, textAlign: 'center',
                animation: isRunning ? 'pulse 1.2s infinite' : 'none',
              }}>
                {meta.icon}
              </span>
              <span style={{ fontSize: 15, minWidth: 22 }}>{agent.icon}</span>
              <span style={{
                fontSize: 13, fontWeight: 600,
                color: st.status === 'done' ? '#0F172A' :
                       st.status === 'running' ? '#0D9488' : '#94A3B8',
                minWidth: 100,
              }}>
                {agent.name}
              </span>
              {st.status === 'done' && (
                <span style={{ fontSize: 11, color: '#64748B', fontFamily: 'monospace' }}>
                  {st.latency}ms
                </span>
              )}
              {st.status === 'skipped' && (
                <span style={{ fontSize: 11, color: '#94A3B8', fontStyle: 'italic' }}>
                  skipped
                </span>
              )}
              {st.summary && (
                <span style={{
                  fontSize: 12, color: '#475569', marginLeft: 6,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  flex: 1,
                }}>
                  {st.summary}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────

function _summarize(data) {
  const a = data.agent;
  if (a === 'Planner' && data.summary)    return data.summary;
  if (a === 'DocSearch') {
    if (data.found > 0)
      return `Found ${data.found} chunks (top: ${data.top_source || '?'} ${data.confidence}%)`;
    return 'No relevant documents';
  }
  if (a === 'Legal') {
    if (data.skipped) return null;
    if (data.mcp_tools && data.mcp_tools.length) {
      return 'Called: ' + data.mcp_tools.join(', ');
    }
    return 'No MCP tools triggered';
  }
  if (a === 'WebResearch') {
    if (data.skipped) return null;
    if (data.found > 0) return `${data.found} web results`;
    return 'No web results';
  }
  if (a === 'Synthesis') {
    return `${data.provider || 'LLM'} (${data.answer_length} chars)`;
  }
  if (a === 'Critic') {
    if (data.skipped) return null;
    if (data.ok)      return 'Passed';
    return 'Issues: ' + (data.issues || []).join(', ');
  }
  return null;
}