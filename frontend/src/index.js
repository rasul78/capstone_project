import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import AppRoot from './AppRoot';

// ErrorBoundary — вместо чёрного экрана показывает ошибку
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error: error.message || String(error) };
  }
  componentDidCatch(error, info) {
    console.error('[Sentinel AI] Crash:', error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh', background: '#F8FAFC',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'Inter, system-ui, sans-serif', padding: 20,
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, padding: '36px 40px',
            maxWidth: 560, width: '100%',
            boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
            border: '1px solid #FECACA',
          }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>
              Sentinel AI — ошибка запуска
            </div>
            <div style={{ fontSize: 13, color: '#64748B', marginBottom: 20, lineHeight: 1.6 }}>
              Приложение не смогло запуститься. Откройте консоль браузера (F12) для деталей.
            </div>
            <pre style={{
              background: '#FEF2F2', border: '1px solid #FECACA',
              borderRadius: 8, padding: '12px 14px',
              fontSize: 12, color: '#DC2626', whiteSpace: 'pre-wrap',
              wordBreak: 'break-word', maxHeight: 200, overflowY: 'auto',
              fontFamily: 'monospace',
            }}>
              {this.state.error}
            </pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: 20, padding: '10px 24px', borderRadius: 9,
                border: 'none', background: '#0D9488', color: '#fff',
                fontSize: 14, fontWeight: 600, cursor: 'pointer',
              }}
            >
              Перезагрузить
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <ErrorBoundary>
    <AppRoot />
  </ErrorBoundary>
);