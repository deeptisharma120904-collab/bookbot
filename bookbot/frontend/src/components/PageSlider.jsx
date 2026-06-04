/**
 * BookBot — PageSlider component.
 * Range slider to set/sync current page with animated visual feedback.
 */

import { useState, useEffect } from 'react';

export default function PageSlider({ currentPage, totalPages, onPageChange, disabled }) {
  const [localPage, setLocalPage] = useState(currentPage);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    setLocalPage(currentPage);
  }, [currentPage]);

  const handleChange = (e) => {
    setLocalPage(parseInt(e.target.value, 10));
    setIsDragging(true);
  };

  const handleCommit = () => {
    setIsDragging(false);
    if (localPage !== currentPage) {
      onPageChange(localPage);
    }
  };

  const progress = totalPages > 0 ? (localPage / totalPages) * 100 : 0;

  // Progress milestone colours
  const barColor =
    progress >= 100
      ? 'from-yellow-400 to-yellow-600'
      : progress >= 75
      ? 'from-green-400 to-cyan-500'
      : progress >= 50
      ? 'from-blue-400 to-purple-500'
      : 'from-purple-500 to-orange-500';

  return (
    <div className="space-y-3 animate-fade-in" id="page-slider-container">
      {/* Label row */}
      <div className="flex items-center justify-between">
        <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse inline-block" />
          Current Page
        </label>
        <div className="flex items-baseline gap-1">
          <span
            className={`text-base font-black transition-all duration-200 ${
              isDragging ? 'text-orange-300 scale-110' : 'text-purple-300'
            }`}
            style={{ transition: 'transform 0.15s cubic-bezier(0.34,1.56,0.64,1), color 0.2s' }}
          >
            {localPage}
          </span>
          <span className="text-xs text-gray-600">/ {totalPages}</span>
        </div>
      </div>

      {/* Slider track */}
      <div className="relative pt-1 pb-1">
        {/* Custom track background */}
        <div className="absolute inset-y-0 my-auto h-2 w-full rounded-full bg-white/5 border border-white/5" style={{ top: '50%', transform: 'translateY(-50%)' }} />

        {/* Filled portion */}
        <div
          className={`absolute my-auto h-2 rounded-full bg-gradient-to-r ${barColor} transition-all duration-300 ease-out`}
          style={{ width: `${progress}%`, top: '50%', transform: 'translateY(-50%)', boxShadow: isDragging ? '0 0 12px rgba(168,85,247,0.5)' : '0 0 6px rgba(168,85,247,0.2)' }}
        />

        {/* Thumb glow */}
        {isDragging && (
          <div
            className="absolute w-5 h-5 rounded-full bg-purple-400/30 blur-md pointer-events-none"
            style={{ left: `calc(${progress}% - 10px)`, top: '50%', transform: 'translateY(-50%)' }}
          />
        )}

        <input
          type="range"
          min={1}
          max={totalPages || 1}
          value={localPage}
          onChange={handleChange}
          onMouseUp={handleCommit}
          onTouchEnd={handleCommit}
          disabled={disabled || totalPages === 0}
          className="relative w-full h-6 appearance-none bg-transparent cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed z-10"
          style={{
            // Thumb styling via CSS custom
            '--thumb-size': isDragging ? '18px' : '14px',
          }}
          id="page-slider"
        />
      </div>

      {/* Progress row */}
      <div className="flex items-center gap-2">
        {/* Mini milestone markers */}
        <div className="flex-1 flex justify-between px-0.5">
          {[25, 50, 75, 100].map((milestone) => (
            <div
              key={milestone}
              className="flex flex-col items-center gap-0.5"
            >
              <div
                className={`w-1 h-1 rounded-full transition-all duration-500 ${
                  progress >= milestone
                    ? 'bg-purple-400 scale-125'
                    : 'bg-white/10'
                }`}
              />
              <span className={`text-[7px] font-bold transition-colors duration-300 ${progress >= milestone ? 'text-purple-400' : 'text-gray-700'}`}>
                {milestone}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Reading progress label */}
      <div className="flex items-center justify-between">
        <span className="text-[9px] text-gray-600 italic">
          {progress >= 100
            ? '🎉 Finished!'
            : progress >= 75
            ? '🏃 Almost there!'
            : progress >= 50
            ? '⚡ Halfway through!'
            : progress >= 25
            ? '📖 Making progress...'
            : '🌱 Just starting...'}
        </span>
        <span className="text-[9px] font-black text-gray-600">
          {Math.round(progress)}%
        </span>
      </div>
    </div>
  );
}
