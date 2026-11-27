import React, { useEffect, useRef } from 'react';
import { AgentRunState, AgentStage } from '../types';

interface Props {
  state: AgentRunState;
  currentStage: AgentStage | null;
}

/**
 * Subtle, editorial ambient canvas (60fps):
 * Soft topographic wave contours on a clean porcelain canvas,
 * providing gentle spatial depth without distracting from content.
 */
export const SpatialScene3D: React.FC<Props> = ({ state }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let rafId = 0;
    let width = 0;
    let height = 0;
    let normX = 0;
    let normY = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const onPointerMove = (e: PointerEvent) => {
      normX = e.clientX / Math.max(1, width) - 0.5;
      normY = e.clientY / Math.max(1, height) - 0.5;
    };

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    let time = 0;

    const render = () => {
      const isRunning = stateRef.current === 'running';
      time += reducedMotion ? 0 : isRunning ? 0.016 : 0.006;

      ctx.clearRect(0, 0, width, height);

      // Soft ambient light wash at top of viewport
      const gx = width * 0.5 + normX * 120;
      const gy = height * 0.12 + normY * 60;
      const grad = ctx.createRadialGradient(gx, gy, 20, gx, gy, Math.max(width, height) * 0.65);
      grad.addColorStop(0, isRunning ? 'rgba(26, 115, 232, 0.07)' : 'rgba(26, 115, 232, 0.045)');
      grad.addColorStop(1, 'rgba(248, 250, 252, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);

      // Subtle architectural wave contours
      const lines = 7;
      ctx.lineWidth = 1;
      for (let l = 0; l < lines; l++) {
        const baseY = height * (0.22 + l * 0.11);
        const alpha = isRunning ? 0.065 : 0.04;
        ctx.strokeStyle = `rgba(100, 116, 139, ${alpha})`;
        ctx.beginPath();
        for (let x = 0; x <= width; x += 36) {
          const u = x / Math.max(1, width);
          const y =
            baseY +
            Math.sin(u * 4.2 + time + l * 0.6) * 18 +
            Math.cos(u * 2.5 - time * 0.7 + l) * 10 +
            normY * 14;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      if (!reducedMotion) {
        rafId = requestAnimationFrame(render);
      }
    };

    render();

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
    };
  }, []);

  return <canvas ref={canvasRef} className="spatial-scene-3d" aria-hidden="true" />;
};
