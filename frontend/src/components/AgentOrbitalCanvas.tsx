import React, { useEffect, useRef } from 'react';
import { AgentRunState, AgentStage } from '../types';

interface Props {
  state: AgentRunState;
  currentStage: AgentStage | null;
}

const STAGE_ORDER: AgentStage[] = [
  'trigger',
  'plan',
  'fetch',
  'extract',
  'verify',
  'dedupe',
  'match',
  'rank',
  'decide',
  'act',
  'report',
];

/**
 * Lightweight 60fps 3D perspective orbital lattice visualizing the
 * 11-stage autonomous state machine & Kill Switch stasis lock.
 */
export const AgentOrbitalCanvas: React.FC<Props> = ({ state, currentStage }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const stateRef = useRef({ state, currentStage });
  stateRef.current = { state, currentStage };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let rafId = 0;
    let angleY = 0.4;
    let angleX = 0.28;

    // 11 orbital stage nodes distributed in 3D Fibonacci sphere
    const nodes = STAGE_ORDER.map((stage, idx) => {
      const phi = Math.acos(1 - (2 * (idx + 0.5)) / STAGE_ORDER.length);
      const theta = Math.PI * (1 + Math.sqrt(5)) * idx;
      return {
        stage,
        x: Math.sin(phi) * Math.cos(theta),
        y: Math.sin(phi) * Math.sin(theta),
        z: Math.cos(phi),
      };
    });

    const render = (timeMs: number) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const { state: curState, currentStage: curStage } = stateRef.current;
      const isKilled = curState === 'killed';
      const isRunning = curState === 'running';

      if (!isKilled) {
        angleY += isRunning ? 0.022 : 0.0055;
        angleX += ((pointerRef.current.y * 0.35 + 0.25) - angleX) * 0.04;
      }

      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.min(w, h) * 0.34;
      const cosY = Math.cos(angleY + pointerRef.current.x * 0.35);
      const sinY = Math.sin(angleY + pointerRef.current.x * 0.35);
      const cosX = Math.cos(angleX);
      const sinX = Math.sin(angleX);

      // Subtle outer telemetry ring
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.24, 0, Math.PI * 2);
      ctx.strokeStyle = isKilled
        ? 'rgba(220, 38, 38, 0.28)'
        : isRunning
        ? 'rgba(79, 70, 229, 0.24)'
        : 'rgba(15, 23, 42, 0.08)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 5]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Project 3D nodes
      const projected = nodes.map((n) => {
        const x1 = n.x * cosY - n.z * sinY;
        const z1 = n.x * sinY + n.z * cosY;
        const y2 = n.y * cosX - z1 * sinX;
        const z2 = n.y * sinX + z1 * cosX;
        const perspective = 2.6 / (2.6 - z2 * 0.65);
        return {
          stage: n.stage,
          sx: cx + x1 * radius * perspective,
          sy: cy + y2 * radius * perspective,
          z: z2,
          scale: perspective,
        };
      });

      // Connect sequential state-machine edges + lattice chords
      for (let i = 0; i < projected.length; i++) {
        const a = projected[i];
        const b = projected[(i + 1) % projected.length];
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.strokeStyle = isKilled
          ? 'rgba(220, 38, 38, 0.25)'
          : isRunning
          ? 'rgba(79, 70, 229, 0.35)'
          : 'rgba(15, 23, 42, 0.14)';
        ctx.lineWidth = 1.1;
        ctx.stroke();

        // Cross-lattice connections for 3D depth
        const c = projected[(i + 4) % projected.length];
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(c.sx, c.sy);
        ctx.strokeStyle = isKilled
          ? 'rgba(220, 38, 38, 0.1)'
          : 'rgba(79, 70, 229, 0.1)';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }

      // Draw central Gateway Core
      const pulse = isKilled ? 1 : 1 + Math.sin(timeMs * 0.004) * (isRunning ? 0.16 : 0.06);
      const coreGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 18 * pulse);
      if (isKilled) {
        coreGrad.addColorStop(0, '#DC2626');
        coreGrad.addColorStop(1, 'rgba(220, 38, 38, 0)');
      } else {
        coreGrad.addColorStop(0, isRunning ? '#4F46E5' : '#3730A3');
        coreGrad.addColorStop(1, 'rgba(79, 70, 229, 0)');
      }
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 18 * pulse, 0, Math.PI * 2);
      ctx.fill();

      // Depth-sort nodes back-to-front
      const sorted = [...projected].sort((p, q) => p.z - q.z);
      for (const p of sorted) {
        const isActiveNode = isRunning && curStage === p.stage;
        const r = (isActiveNode ? 5.2 : 3.2) * p.scale;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
        if (isKilled) {
          ctx.fillStyle = p.z > 0 ? '#DC2626' : '#FCA5A5';
        } else if (isActiveNode) {
          ctx.fillStyle = '#4F46E5';
        } else {
          ctx.fillStyle = p.z > 0 ? '#0F172A' : '#94A3B8';
        }
        ctx.fill();

        if (isActiveNode) {
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(79, 70, 229, 0.45)';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }

      rafId = requestAnimationFrame(render);
    };

    rafId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return (
    <div
      className="orbital-stage"
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        pointerRef.current = {
          x: ((e.clientX - rect.left) / rect.width - 0.5) * 2,
          y: ((e.clientY - rect.top) / rect.height - 0.5) * 2,
        };
      }}
      onMouseLeave={() => {
        pointerRef.current = { x: 0, y: 0 };
      }}
      title="Interactive 3D 11-Stage Autonomous State Machine"
    >
      <canvas ref={canvasRef} className="orbital-canvas" />
      <div className="orbital-caption">
        <span className="mono">
          {state === 'killed'
            ? 'GATEWAY LOCKED'
            : state === 'running' && currentStage
            ? `STAGE: ${currentStage.toUpperCase()}`
            : 'TOOL GATEWAY · 11 STAGES'}
        </span>
      </div>
    </div>
  );
};
