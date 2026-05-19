import React from 'react';

export default function Card({ children, style = {}, glass = false, accent }) {
  return (
    <div style={{
      background: glass ? 'rgba(255,255,255,0.02)' : 'rgba(14,16,28,0.8)',
      border: `1px solid ${accent ? accent + '25' : 'rgba(255,255,255,0.05)'}`,
      borderRadius: 16,
      ...(accent ? { boxShadow: `0 0 0 1px ${accent}10 inset` } : {}),
      ...style,
    }}>
      {children}
    </div>
  );
}