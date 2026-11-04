/**
 * BookBot — BookIngest component.
 * Drag & drop PDF or paste text to ingest a book, with rich animations.
 * Progress bar polls the real /api/books/{book_id}/status endpoint for PDFs.
 */

import { useState, useRef, useEffect, useCallback } from 'react';

const API_BASE = '/api';

/** Poll /api/books/{book_id}/status until completed or failed. */
async function pollIngestionStatus(bookId, onProgress, signal) {
  const MAX_ATTEMPTS = 120; // 120 × 2s = 4 minutes max
  let attempt = 0;
  while (attempt < MAX_ATTEMPTS) {
    if (signal?.aborted) return;
    try {
      const res = await fetch(`${API_BASE}/books/${bookId}/status`);
      if (res.ok) {
        const data = await res.json();
        const pct = data.progress_percentage ?? 0;
        onProgress(pct, data.status);
        if (data.status === 'completed' || data.status === 'failed') return;
      }
    } catch (_) {
      // Network blip — keep polling
    }
    await new Promise((r) => setTimeout(r, 2000));
    attempt++;
  }
}

export default function BookIngest({ onIngestText, onIngestPdf, loading }) {
  const [mode, setMode] = useState('text');
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [bookId, setBookId] = useState('');
  const [content, setContent] = useState('');
  const [pdfFile, setPdfFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState(null);
  const [ingestProgress, setIngestProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [isPolling, setIsPolling] = useState(false);
  const fileInputRef = useRef(null);
  const abortRef = useRef(null);

  // For plain-text ingest (synchronous), keep the fake animation
  useEffect(() => {
    if (mode !== 'text') return;
    if (loading) {
      setIngestProgress(0);
      let p = 0;
      const interval = setInterval(() => {
        p += Math.random() * 15;
        if (p >= 95) { clearInterval(interval); p = 95; }
        setIngestProgress(p);
      }, 250);
      return () => clearInterval(interval);
    } else {
      if (ingestProgress > 0 && !isPolling) {
        setIngestProgress(100);
        setTimeout(() => setIngestProgress(0), 800);
      }
    }
  }, [loading, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const generateBookId = (t) =>
    t.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

  const handleTitleChange = (e) => {
    setTitle(e.target.value);
    if (!bookId || bookId === generateBookId(title)) {
      setBookId(generateBookId(e.target.value));
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type === 'application/pdf') {
      setPdfFile(file);
      setMode('pdf');
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setPdfFile(file);
      setMode('pdf');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title || !author || !bookId) {
      setStatus({ type: 'error', message: 'Please fill in all fields.' });
      return;
    }
    setStatus(null);
    setIngestProgress(0);
    setProgressStatus('');

    // Cancel any previous poll
    if (abortRef.current) abortRef.current.abort();

    try {
      if (mode === 'pdf' && pdfFile) {
        const formData = new FormData();
        formData.append('file', pdfFile);
        formData.append('book_id', bookId);
        formData.append('title', title);
        formData.append('author', author);

        // Start upload — backend responds immediately, then processes in background
        setIngestProgress(5);
        setProgressStatus('Uploading...');
        const result = await onIngestPdf(formData);

        // Now poll the real status endpoint
        setIsPolling(true);
        setIngestProgress(10);
        setProgressStatus('Processing pages...');
        const ctrl = new AbortController();
        abortRef.current = ctrl;

        await pollIngestionStatus(
          result.book_id ?? bookId,
          (pct, st) => {
            setIngestProgress(pct);
            if (st === 'completed') setProgressStatus('Complete!');
            else if (st === 'failed') setProgressStatus('Failed');
            else setProgressStatus(`Processing... ${Math.round(pct)}%`);
          },
          ctrl.signal
        );

        setIsPolling(false);
        setIngestProgress(100);
        setProgressStatus('Complete!');
        setStatus({
          type: 'success',
          message: `"${result.title}" — ${result.total_pages} pages ingested!`,
        });
        setTimeout(() => setIngestProgress(0), 1200);

      } else if (mode === 'text' && content) {
        const result = await onIngestText({ book_id: bookId, title, author, content });
        setStatus({
          type: 'success',
          message: `"${result.title}" — ${result.total_pages} pages ingested!`,
        });
      } else {
        setStatus({ type: 'error', message: 'Please provide book content (text or PDF).' });
        return;
      }
      setTitle(''); setAuthor(''); setBookId(''); setContent(''); setPdfFile(null);
    } catch (err) {
      setIsPolling(false);
      setIngestProgress(0);
      setStatus({ type: 'error', message: `${err.message}` });
    }
  };

  const inputClass =
    'w-full px-3 py-2.5 rounded-xl glass-light text-sm text-white placeholder-gray-600 ' +
    'focus:outline-none transition-all duration-300 border border-transparent focus:border-purple-500/30';

  const showProgress = loading || isPolling;

  return (
    <form onSubmit={handleSubmit} className="space-y-3 animate-fade-in" id="ingest-form">

      {/* Mode Toggle */}
      <div className="relative flex rounded-xl overflow-hidden border border-white/8 p-0.5 bg-white/3">
        {/* Sliding pill */}
        <div
          className="absolute top-0.5 bottom-0.5 w-[calc(50%-2px)] rounded-lg bg-purple-600/40 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]"
          style={{ left: mode === 'text' ? '2px' : 'calc(50%)' }}
        />
        <button
          type="button"
          onClick={() => setMode('text')}
          className={`relative flex-1 py-2 px-3 text-xs font-bold transition-all duration-200 cursor-pointer rounded-lg z-10 ${
            mode === 'text' ? 'text-purple-200' : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Paste Text
        </button>
        <button
          type="button"
          onClick={() => setMode('pdf')}
          className={`relative flex-1 py-2 px-3 text-xs font-bold transition-all duration-200 cursor-pointer rounded-lg z-10 ${
            mode === 'pdf' ? 'text-purple-200' : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Upload PDF
        </button>
      </div>

      {/* Metadata Fields */}
      <div className="space-y-2">
        <input
          type="text" value={title} onChange={handleTitleChange}
          placeholder="Book Title"
          className={inputClass}
          id="book-title-input"
        />
        <input
          type="text" value={author} onChange={(e) => setAuthor(e.target.value)}
          placeholder="Author"
          className={inputClass}
          id="book-author-input"
        />
        <input
          type="text" value={bookId} onChange={(e) => setBookId(e.target.value)}
          placeholder="Book ID (auto-generated)"
          className={`${inputClass} text-gray-500 text-xs`}
          id="book-id-input"
        />
      </div>

      {/* Content Input — animated transition */}
      <div className="animate-slide-up" key={mode}>
        {mode === 'text' ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={"Paste book content here...\n\nUse '--- PAGE 1 ---' markers to define pages, or content will be auto-chunked."}
            rows={5}
            className={`${inputClass} resize-none`}
            id="book-content-input"
          />
        ) : (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center p-5 rounded-xl border-2 border-dashed
                        transition-all duration-300 cursor-pointer relative overflow-hidden ${
              dragOver
                ? 'border-purple-400 bg-purple-500/10 scale-[1.02]'
                : pdfFile
                ? 'border-green-500/40 bg-green-500/5'
                : 'border-white/10 hover:border-purple-500/30 hover:bg-white/[0.03]'
            }`}
            id="pdf-drop-zone"
          >
            {dragOver && (
              <>
                <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-purple-400 rounded-tl animate-pop-in" />
                <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-purple-400 rounded-tr animate-pop-in" />
                <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-purple-400 rounded-bl animate-pop-in" />
                <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-purple-400 rounded-br animate-pop-in" />
              </>
            )}

            <input
              ref={fileInputRef}
              type="file" accept=".pdf"
              onChange={handleFileSelect}
              className="hidden"
            />

            {pdfFile ? (
              <div className="text-center animate-pop-in">
                <span className="text-3xl block mb-2 animate-float">📄</span>
                <p className="text-sm text-green-400 font-bold">{pdfFile.name}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {pdfFile.size < 1024 * 1024
                    ? `${(pdfFile.size / 1024).toFixed(1)} KB`
                    : `${(pdfFile.size / 1024 / 1024).toFixed(2)} MB`}{' '}
                  — Click to change
                </p>
              </div>
            ) : (
              <div className="text-center">
                <span className={`text-3xl block mb-2 transition-all duration-300 ${dragOver ? 'animate-float scale-110' : 'opacity-40'}`}>
                  📁
                </span>
                <p className="text-sm text-gray-400">
                  {dragOver ? 'Drop it!' : 'Drop PDF here or click to browse'}
                </p>
                <p className="text-[10px] text-gray-600 mt-1">Supports .pdf files</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Progress Bar — real polling for PDF, fake animation for text */}
      {showProgress && ingestProgress > 0 && (
        <div className="space-y-1.5 animate-fade-in">
          <div className="flex justify-between items-center">
            <span className="text-[10px] text-purple-400 font-bold animate-pulse">
              {progressStatus || 'Processing book...'}
            </span>
            <span className="text-[10px] text-gray-600">{Math.round(ingestProgress)}%</span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-purple-500 to-orange-500 transition-all duration-500 ease-out"
              style={{ width: `${ingestProgress}%`, boxShadow: '0 0 8px rgba(168,85,247,0.5)' }}
            />
          </div>
        </div>
      )}

      {/* Status Message */}
      {status && (
        <div
          className={`px-3 py-2.5 rounded-xl text-xs font-medium animate-slide-up border ${
            status.type === 'success'
              ? 'bg-green-500/8 text-green-300 border-green-500/20'
              : 'bg-red-500/8 text-red-300 border-red-500/20'
          }`}
        >
          {status.message}
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={loading || isPolling || !title || !author}
        className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white text-sm font-bold
                   hover:from-purple-500 hover:to-indigo-500 disabled:opacity-25 disabled:cursor-not-allowed
                   transition-all duration-300 hover:shadow-xl hover:shadow-purple-500/25
                   active:scale-95 cursor-pointer btn-ripple neon-glow"
        id="ingest-submit-button"
      >
        {(loading || isPolling) ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {isPolling ? 'Indexing Pages...' : 'Uploading...'}
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            Ingest Book
          </span>
        )}
      </button>
    </form>
  );
}
