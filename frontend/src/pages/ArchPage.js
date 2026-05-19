import React, { useState } from 'react';
import { useStore } from '../store/index';
import PageHeader from '../components/PageHeader';

const MONO = "'JetBrains Mono', monospace";

function LayerBlock({ label, detail, shape, color, width = '100%', highlight = false }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width, margin: '0 auto 5px',
        background: hov ? color + '20' : color + '0d',
        border: `1px solid ${hov || highlight ? color + '40' : color + '20'}`,
        borderRadius: 10, padding: '9px 14px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        transition: 'all .15s', cursor: 'default',
      }}
    >
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color, lineHeight: 1.3 }}>{label}</div>
        {detail && <div style={{ fontSize: 10, color: '#E2E8F0', marginTop: 2, fontFamily: MONO }}>{detail}</div>}
      </div>
      <div style={{
        fontSize: 10, fontFamily: MONO, color: color + 'bb',
        background: color + '14', padding: '3px 8px', borderRadius: 5,
        border: `1px solid ${color}20`, whiteSpace: 'nowrap', flexShrink: 0, marginLeft: 10,
      }}>{shape}</div>
    </div>
  );
}

function Arrow({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0', justifyContent: 'center' }}>
      <div style={{ width: 1, height: 14, background: '#E2E8F0', margin: '0 auto' }} />
      {label && <div style={{ fontSize: 9, color: '#E2E8F0', fontFamily: MONO, position: 'absolute' }}>{label}</div>}
    </div>
  );
}

function ResCard({ idx, inCh, outCh, stride }) {
  return (
    <div style={{
      background: 'rgba(12,14,24,0.8)', border: '1px solid #E2E8F0',
      borderRadius: 14, padding: '14px 16px', marginBottom: 8,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: 20, height: 20, borderRadius: 6,
          background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.3)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontFamily: MONO,
        }}>{idx}</span>
        ResidualBlock + SE Attention
        {stride > 1 && <span style={{ fontSize: 9, color: '#E2E8F0', fontFamily: MONO }}>stride={stride} ↓</span>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 100px', gap: 10 }}>
        {/* Main path */}
        <div>
          <div style={{ fontSize: 9, color: '#E2E8F0', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 6 }}>MAIN PATH</div>
          {[
            `Conv2d(${inCh}→${outCh}, 3×3${stride > 1 ? ', s='+stride : ''})`,
            'BatchNorm2d → ReLU',
            `Conv2d(${outCh}→${outCh}, 3×3)`,
            'BatchNorm2d',
          ].map((l, i) => (
            <div key={i} style={{
              fontSize: 10, padding: '4px 8px', borderRadius: 5, marginBottom: 3,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.12)',
              color: '#E2E8F0', fontFamily: MONO,
            }}>{l}</div>
          ))}
        </div>
        {/* Skip */}
        <div>
          <div style={{ fontSize: 9, color: '#E2E8F0', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 6 }}>SKIP</div>
          <div style={{
            fontSize: 10, padding: '4px 8px', borderRadius: 5,
            background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.15)',
            color: '#8b5cf6', fontFamily: MONO, textAlign: 'center',
          }}>
            {inCh !== outCh || stride > 1 ? `Conv1×1\n+BN` : 'identity'}
          </div>
          <div style={{
            marginTop: 6, fontSize: 9, color: '#8b5cf6', fontFamily: MONO, textAlign: 'center',
            background: 'rgba(139,92,246,0.06)', borderRadius: 5, padding: '3px',
          }}>⊕ add</div>
        </div>
        {/* SE */}
        <div>
          <div style={{ fontSize: 9, color: '#E2E8F0', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 6 }}>SE ATTN</div>
          {[
            `AvgPool→[B,${outCh}]`,
            `FC(${outCh}→${outCh>>4})`,
            `ReLU`,
            `FC→${outCh}`,
            'Sigmoid × x',
          ].map((l, i) => (
            <div key={i} style={{
              fontSize: 9, padding: '3px 7px', borderRadius: 4, marginBottom: 2,
              background: 'rgba(124,58,237,0.06)', border: '1px solid rgba(124,58,237,0.12)',
              color: '#7c3aed', fontFamily: MONO,
            }}>{l}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ArchPage() {
  const { modelInfo } = useStore();
  const p = modelInfo?.total_params_fmt || '~2.5M';

  const concepts = [
    { icon: '↩', title: 'Skip Connections', body: 'F(x) + x — градиент проходит напрямую через всю сеть. Решает проблему исчезновения градиентов в глубоких сетях (ResNet, 2015).', color: '#6366f1' },
    { icon: '🎯', title: 'SE Attention', body: 'Squeeze-and-Excitation: учим сеть взвешивать важность каждого канала. AvgPool сжимает пространство → FC учит веса → Sigmoid масштабирует.', color: '#a78bfa' },
    { icon: '⚖', title: 'Batch Normalization', body: 'Нормализует активации внутри мини-батча. Ускоряет обучение, уменьшает чувствительность к инициализации весов.', color: '#22d3a5' },
    { icon: '📐', title: 'Kaiming Init', body: 'Инициализация весов Conv2d по He (2015) для ReLU-активаций. Сохраняет дисперсию сигнала на входе и выходе каждого слоя.', color: '#fbbf24' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <PageHeader icon="⬡" title="Архитектура VisionNet" subtitle={`собственная CNN · ResNet-style · SE Attention · ${p} параметров`} />

      <div style={{ flex: 1, overflow: 'auto', padding: '22px 28px', display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: 18 }}>
        {/* Layer graph */}
        <div style={{
          background: '#fff', border: '1px solid #E2E8F0',
          borderRadius: 16, padding: '18px 16px', overflowY: 'auto',
        }}>
          <div style={{ fontSize: 10, color: '#E2E8F0', fontFamily: MONO, letterSpacing: '0.1em', marginBottom: 14 }}>
            ВЫЧИСЛИТЕЛЬНЫЙ ГРАФ
          </div>
          <LayerBlock label="Input Image" detail="изображение пользователя" shape="B × 3 × 32 × 32" color="#6b7280" />
          <Arrow /><LayerBlock label="Stem: Conv2d" detail="3→64, 3×3, padding=1" shape="B × 64 × 32 × 32" color="#818cf8" />
          <Arrow /><LayerBlock label="BatchNorm2d + ReLU" detail="нормализация активаций" shape="B × 64 × 32 × 32" color="#6366f1" />
          <Arrow /><LayerBlock label="Stage 1: ResBlock + SE" detail="64→64, stride=1" shape="B × 64 × 32 × 32" color="#4f46e5" highlight />
          <Arrow /><LayerBlock label="Stage 2: ResBlock + SE" detail="64→128, stride=2 ↓" shape="B × 128 × 16 × 16" color="#4338ca" highlight />
          <Arrow /><LayerBlock label="Stage 3: ResBlock + SE" detail="128→256, stride=2 ↓" shape="B × 256 × 8 × 8" color="#3730a3" highlight />
          <Arrow /><LayerBlock label="Stage 4: ResBlock + SE" detail="256→512, stride=2 ↓" shape="B × 512 × 4 × 4" color="#312e81" highlight />
          <Arrow /><LayerBlock label="Global Avg Pool" detail="AdaptiveAvgPool2d(1)" shape="B × 512 × 1 × 1" color="#7c3aed" />
          <Arrow /><LayerBlock label="Flatten" detail="" shape="B × 512" color="#6d28d9" />
          <Arrow /><LayerBlock label="FC: 512→256" detail="Linear + ReLU + Dropout(0.3)" shape="B × 256" color="#8b5cf6" />
          <Arrow /><LayerBlock label="FC: 256→10" detail="логиты классов" shape="B × 10" color="#a78bfa" />
          <Arrow /><LayerBlock label="Softmax" detail="вероятности → предсказание" shape="B × 10" color="#22d3a5" />

          {/* Param count */}
          <div style={{
            marginTop: 14, padding: '12px 14px',
            background: 'rgba(6,8,14,0.8)', borderRadius: 10,
            border: '1px solid #E2E8F0', fontFamily: MONO,
          }}>
            {[
              ['Stem', '~37K'],
              ['Stage 1', '~148K'],
              ['Stage 2', '~525K'],
              ['Stage 3', '~1.97M'],
              ['Head FC', '~140K'],
              ['ИТОГО', p],
            ].map(([k, v]) => (
              <div key={k} style={{
                display: 'flex', justifyContent: 'space-between', padding: '3px 0',
                borderBottom: k === 'ИТОГО' ? 'none' : '1px solid #E2E8F0',
                marginBottom: k === 'Stage 4' ? 6 : 0,
              }}>
                <span style={{ fontSize: 10, color: k === 'ИТОГО' ? '#a78bfa' : '#E2E8F0' }}>{k}</span>
                <span style={{ fontSize: 10, color: k === 'ИТОГО' ? '#a78bfa' : '#E2E8F0', fontWeight: k === 'ИТОГО' ? 700 : 400 }}>{v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
          {/* Residual blocks */}
          <ResCard idx={1} inCh={64}  outCh={64}  stride={1} />
          <ResCard idx={2} inCh={64}  outCh={128} stride={2} />
          <ResCard idx={3} inCh={128} outCh={256} stride={2} />
          <ResCard idx={4} inCh={256} outCh={512} stride={2} />

          {/* Key concepts */}
          <div style={{
            background: '#fff', border: '1px solid #E2E8F0',
            borderRadius: 14, padding: '16px 18px',
          }}>
            <div style={{ fontSize: 10, color: '#E2E8F0', fontFamily: MONO, letterSpacing: '0.1em', marginBottom: 14 }}>
              КЛЮЧЕВЫЕ КОНЦЕПЦИИ
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {concepts.map(c => (
                <div key={c.title} style={{
                  background: '#F8FAFC', border: `1px solid ${c.color}33`,
                  borderRadius: 10, padding: '12px 14px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                    <span style={{ fontSize: 16 }}>{c.icon}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: c.color }}>{c.title}</span>
                  </div>
                  <p style={{ fontSize: 11, color: '#E2E8F0', lineHeight: 1.55, margin: 0 }}>
                    {c.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}