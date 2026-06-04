/**
 * BookBot — StatsDashboard component.
 * Displays XP, Level, Streak, and Badges with rich animations.
 */

import { useEffect, useRef } from 'react';

export default function StatsDashboard({ stats }) {
  const xpToNextLevel = 1000 - (stats.xp % 1000);
  const progress = Math.round((stats.xp % 1000) / 10); // 0–100

  // Animate XP bar fill on change
  const barRef = useRef(null);
  useEffect(() => {
    if (barRef.current) {
      barRef.current.style.setProperty('--xp-width', `${progress}%`);
      barRef.current.style.width = `${progress}%`;
    }
  }, [progress]);

  return (
    <div className="space-y-4 animate-fade-in">

      {/* ── XP & Level Card ─────────────────────────────────── */}
      <div className="relative p-4 rounded-2xl overflow-hidden glass border border-orange-500/15 shadow-lg shadow-orange-500/5 group card-hover">
        {/* Animated background glow */}
        <div className="absolute inset-0 bg-gradient-to-br from-orange-500/5 via-transparent to-purple-500/5 group-hover:from-orange-500/10 group-hover:to-purple-500/10 transition-all duration-700" />

        <div className="relative z-10 flex justify-between items-end mb-3">
          <div>
            <p className="text-[9px] font-black text-orange-400 uppercase tracking-[0.15em] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse inline-block" />
              Level
            </p>
            <h3 className="text-3xl font-black text-white mt-0.5 leading-none">{stats.level}</h3>
          </div>
          <div className="text-right">
            <p className="text-[9px] font-black text-gray-600 uppercase tracking-[0.1em]">Total XP</p>
            <p className="text-base font-black text-orange-200">{stats.xp.toLocaleString()}</p>
          </div>
        </div>

        {/* XP Progress Bar */}
        <div className="h-2.5 w-full bg-white/5 rounded-full overflow-hidden relative z-10 border border-white/5">
          {/* Glow behind bar */}
          <div
            className="absolute inset-0 blur-sm opacity-60 transition-all duration-1000 ease-out"
            style={{ width: `${progress}%`, background: 'linear-gradient(90deg,#a855f7,#fb923c)' }}
          />
          {/* Main fill */}
          <div
            ref={barRef}
            className="h-full rounded-full relative transition-all duration-1000 ease-[cubic-bezier(0.34,1.56,0.64,1)]"
            style={{
              width: `${progress}%`,
              background: 'linear-gradient(90deg, #a855f7, #fb923c, #fbbf24)',
              backgroundSize: '200% 100%',
              animation: 'shimmer 2.5s linear infinite',
            }}
          />
          {/* Shine sweep */}
          <div
            className="absolute top-0 h-full w-8 rounded-full"
            style={{
              left: `${Math.max(progress - 5, 0)}%`,
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
              transition: 'left 1s ease-out',
            }}
          />
        </div>

        <p className="text-[9px] text-gray-600 mt-2 text-center relative z-10">
          <span className="text-orange-400 font-bold">{xpToNextLevel} XP</span> to level {stats.level + 1}
        </p>
      </div>

      {/* ── Streak ─────────────────────────────────────────── */}
      <div className="flex items-center gap-4 p-3 rounded-2xl glass-light border border-white/5 card-hover group">
        <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center text-2xl flex-shrink-0">
          <span className="animate-fire-pulse inline-block">🔥</span>
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-black text-white leading-none">
            {stats.streak} <span className="font-medium text-orange-300">Day{stats.streak !== 1 ? 's' : ''}</span>
          </h4>
          <p className="text-[9px] text-gray-600 uppercase tracking-wider mt-0.5">Reading streak</p>

          {/* Streak dots */}
          <div className="flex gap-1 mt-2">
            {Array.from({ length: Math.min(stats.streak, 7) }).map((_, i) => (
              <span
                key={i}
                className="w-2 h-2 rounded-full bg-orange-400 animate-pop-in"
                style={{ animationDelay: `${i * 0.08}s`, opacity: 0.5 + (i / 7) * 0.5 }}
              />
            ))}
            {stats.streak === 0 && (
              <span className="text-[9px] text-gray-700 italic">Start reading to build your streak!</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Pages Read ──────────────────────────────────────── */}
      {stats.total_pages_read > 0 && (
        <div className="flex items-center justify-between p-3 rounded-xl glass border border-white/5 card-hover">
          <div className="flex items-center gap-2">
            <span className="text-lg">📄</span>
            <span className="text-xs text-gray-400">Pages Read</span>
          </div>
          <span className="text-sm font-black text-purple-300">{stats.total_pages_read.toLocaleString()}</span>
        </div>
      )}

      {/* ── Badges ──────────────────────────────────────────── */}
      <div>
        <h4 className="text-[9px] font-black text-gray-500 uppercase tracking-[0.15em] mb-3 px-1 flex items-center gap-2">
          <span>🏅</span> Badges Unlocked
          {stats.badges.length > 0 && (
            <span className="ml-auto px-1.5 py-0.5 rounded-full bg-orange-500/15 text-orange-400 text-[8px] font-black">
              {stats.badges.length}
            </span>
          )}
        </h4>

        {stats.badges.length === 0 ? (
          <div className="p-4 text-center rounded-xl border border-dashed border-white/8">
            <p className="text-2xl mb-1">🔒</p>
            <p className="text-xs text-gray-700 italic">Keep reading to earn badges</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {stats.badges.map((badge, i) => (
              <div
                key={badge}
                className="p-2 rounded-xl glass border border-orange-500/10 flex flex-col items-center text-center
                           animate-badge-unlock badge-pop card-hover cursor-default
                           hover:border-orange-500/30 hover:bg-orange-500/5"
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                <span className="text-2xl mb-1 drop-shadow-lg">{getBadgeEmoji(badge)}</span>
                <span className="text-[9px] font-black text-gray-400 leading-tight">{badge}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function getBadgeEmoji(name) {
  const emojis = {
    'First Chapter': '🏁',
    'Night Owl':     '🦉',
    'Speed Reader':  '⚡',
    'Curious Mind':  '🧐',
    'Halfway Hero':  '🏆',
    'Bookworm':      '🐛',
  };
  return emojis[name] || '🏅';
}
