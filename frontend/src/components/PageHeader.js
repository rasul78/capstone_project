import React from 'react';

const MONO = "'JetBrains Mono', monospace";

export default function PageHeader({ icon, title, subtitle, right }) {
  return (
    <div style={{
      padding: '18px 28px 16px',
      borderBottom: '1px solid #E2E8F0',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      flexShrink: 0, background: '#fff',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'linear-gradient(135deg, #EFF6FF, #F5F3FF)',
          border: '1px solid #BFDBFE',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16, flexShrink: 0,
        }}>{icon}</span>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', letterSpacing: '-0.01em' }}>
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2, fontFamily: MONO }}>
              {subtitle}
            </div>
          )}
        </div>
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}
