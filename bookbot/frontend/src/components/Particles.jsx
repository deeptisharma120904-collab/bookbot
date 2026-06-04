/**
 * BookBot — Particles Component.
 * Renders animated floating particles on a canvas for ambient depth.
 */

import { useEffect, useRef } from 'react';

export default function Particles() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let animId;
    const particles = [];
    const PARTICLE_COUNT = 40;

    // Color palette matching the app theme
    const colors = [
      'rgba(192, 132, 252,', // purple
      'rgba(251, 146,  60,', // orange
      'rgba( 34, 211, 238,', // cyan
      'rgba(129, 140, 248,', // blue
      'rgba(251, 191,  36,', // gold
    ];

    function resize() {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    }

    function createParticle() {
      const color = colors[Math.floor(Math.random() * colors.length)];
      return {
        x: Math.random() * canvas.width,
        y: canvas.height + Math.random() * 100,
        radius: Math.random() * 2.5 + 0.5,
        speedY: -(Math.random() * 0.6 + 0.2),
        speedX: (Math.random() - 0.5) * 0.4,
        opacity: 0,
        maxOpacity: Math.random() * 0.55 + 0.15,
        fadeIn: true,
        color,
        twinkle: Math.random() * Math.PI * 2,
        twinkleSpeed: Math.random() * 0.03 + 0.01,
      };
    }

    resize();
    window.addEventListener('resize', resize);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const p = createParticle();
      p.y = Math.random() * canvas.height; // Spread initial positions
      particles.push(p);
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach((p, i) => {
        // Twinkle
        p.twinkle += p.twinkleSpeed;
        const twinkledOpacity = p.opacity * (0.7 + 0.3 * Math.sin(p.twinkle));

        // Fade in/out
        if (p.fadeIn) {
          p.opacity = Math.min(p.opacity + 0.004, p.maxOpacity);
          if (p.opacity >= p.maxOpacity) p.fadeIn = false;
        } else {
          p.opacity = Math.max(p.opacity - 0.002, 0);
        }

        // Move
        p.y += p.speedY;
        p.x += p.speedX;

        // Reset when out of view
        if (p.y < -20 || p.opacity <= 0) {
          particles[i] = createParticle();
          return;
        }

        // Draw glow
        const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius * 4);
        gradient.addColorStop(0, `${p.color} ${twinkledOpacity})`);
        gradient.addColorStop(1, `${p.color} 0)`);

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius * 4, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Draw core dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color} ${twinkledOpacity})`;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      id="particles-canvas"
      style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1 }}
    />
  );
}
