/**
 * BookBot — Main Application.
 * Premium dark-mode layout with sidebar controls and central chat widget.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useBookBot } from './hooks/useBookBot';
import ChatWidget from './components/ChatWidget';
import BookIngest from './components/BookIngest';
import PageSlider from './components/PageSlider';
import StatsDashboard from './components/StatsDashboard';
import BookReader from './components/BookReader';
import Particles from './components/Particles';
import confetti from 'canvas-confetti';
import './index.css';

// Pre-compute static style objects to prevent unnecessary garbage collection on every render
const bgGlowStyle1 = { animationDelay: '0s' };
const bgGlowStyle2 = { animationDelay: '-6s' };
const bgGlowStyle3 = { animationDelay: '-12s' };
const bookDelayStyles = Array.from({ length: 50 }, (_, i) => ({ animationDelay: `${i * 0.08}s` }));

function App() {
  const {
    ingestLoading,
    chatLoading,
    error,
    books,
    stats,
    ingestBook,
    ingestBookPdf,
    deleteBook,
    clearAllBooks,
    sendMessage,
    syncPage,
    getSuggestions,
    getQuote,
    getPage,
    getSession,
    listBooks,
    clearError,
  } = useBookBot();

  const [selectedBook, setSelectedBook] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [userId] = useState('user_1');
  const [showIngest, setShowIngest] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sessionQuote, setSessionQuote] = useState(null);
  const [levelUpVisible, setLevelUpVisible] = useState(false);
  const [newBadge, setNewBadge] = useState(null);

  const [bookToDelete, setBookToDelete] = useState(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = useCallback((msg) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  }, []);

  const handleConfirmDeleteBook = useCallback(async () => {
    if (!bookToDelete) return;
    setDeleting(true);
    try {
      await deleteBook(bookToDelete.book_id);
      if (selectedBook?.book_id === bookToDelete.book_id) {
        setSelectedBook(null);
        setSessionQuote(null);
      }
      showToast(`Removed "${bookToDelete.title}" and its content data.`);
      setBookToDelete(null);
    } catch (err) {
      // Handled in hook
    } finally {
      setDeleting(false);
    }
  }, [bookToDelete, deleteBook, selectedBook, showToast]);

  const handleConfirmClearAll = useCallback(async () => {
    setDeleting(true);
    try {
      await clearAllBooks();
      setSelectedBook(null);
      setSessionQuote(null);
      showToast('Cleared all books and content data.');
      setShowClearConfirm(false);
    } catch (err) {
      // Handled in hook
    } finally {
      setDeleting(false);
    }
  }, [clearAllBooks, showToast]);

  // Load books on mount
  useEffect(() => {
    listBooks();
  }, [listBooks]);

  // Handle book selection — restores saved page progress from the backend session
  const handleBookSelect = useCallback(async (book) => {
    setSelectedBook(book);
    setShowIngest(false);
    // Restore last saved page for this user+book, fallback to page 1
    const session = await getSession(userId, book.book_id);
    const savedPage = session?.current_page ?? 1;
    setCurrentPage(Math.max(1, Math.min(savedPage, book.total_pages)));
    getQuote(book.book_id, savedPage).then((quote) => {
      if (quote) setSessionQuote(quote);
    });
  }, [getQuote, getSession, userId]);

  // Handle page change — clamp to valid range to prevent out-of-bounds API calls
  const handlePageChange = useCallback(async (page) => {
    if (!selectedBook) return;
    const clamped = Math.max(1, Math.min(page, selectedBook.total_pages));
    setCurrentPage(clamped);
    await syncPage(userId, selectedBook.book_id, clamped);
  }, [selectedBook, userId, syncPage]);

  // Track level-ups and badge unlocks with celebrations
  const lastLevel = useRef(stats.level);
  const lastBadgeCount = useRef(stats.badges.length);

  useEffect(() => {
    if (stats.level > lastLevel.current) {
      setLevelUpVisible(true);
      setTimeout(() => setLevelUpVisible(false), 3000);
      confetti({
        particleCount: 200,
        spread: 80,
        origin: { y: 0.55 },
        colors: ['#c084fc', '#fb923c', '#fbbf24', '#22d3ee', '#ffffff'],
        ticks: 300,
      });
      lastLevel.current = stats.level;
    }
    if (stats.badges.length > lastBadgeCount.current) {
      const latestBadge = stats.badges[stats.badges.length - 1];
      setNewBadge(latestBadge);
      setTimeout(() => setNewBadge(null), 3500);
      confetti({ particleCount: 100, angle: 60,  spread: 55, origin: { x: 0 }, colors: ['#fbbf24', '#fb923c'] });
      confetti({ particleCount: 100, angle: 120, spread: 55, origin: { x: 1 }, colors: ['#fbbf24', '#fb923c'] });
      lastBadgeCount.current = stats.badges.length;
    }
  }, [stats.level, stats.badges.length]);

  const handleSendMessage = useCallback(async ({ message, history }) => {
    if (!selectedBook) throw new Error('No book selected');
    return await sendMessage({
      user_id: userId,
      book_id: selectedBook.book_id,
      current_page: currentPage,
      message,
      history,
    });
  }, [selectedBook, userId, currentPage, sendMessage]);

  const handleIngestSuccess = useCallback(async (ingestFn, data) => {
    const result = await ingestFn(data);
    await listBooks();
    // Auto-select the newly uploaded book so the user sees the processing UI
    // (BookReader polls until ingestion completes, per Issue 14 fix)
    if (result?.book_id) {
      setSelectedBook({
        book_id: result.book_id,
        title: result.title ?? data.title ?? 'Untitled',
        author: data.author ?? 'Unknown',
        total_pages: result.total_pages ?? 1,
      });
      setCurrentPage(1);
      setShowIngest(false);
    }
    return result;
  }, [listBooks]);

  return (
    <div className="h-screen flex overflow-hidden relative">
      {/* ── Animated Background Layers ──────────────────────────── */}
      <div className="aurora-bg" />
      <div className="bg-radial-glow bg-purple-600/50 -top-40 -left-40" style={bgGlowStyle1} />
      <div className="bg-radial-glow bg-indigo-600/30 top-1/2 -right-20" style={bgGlowStyle2} />
      <div className="bg-radial-glow bg-orange-600/20 -bottom-40 left-1/3" style={bgGlowStyle3} />
      <div className="bg-grid absolute inset-0 z-0" />
      <Particles />

      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`relative z-10 flex flex-col border-r border-white/5 transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
          sidebarCollapsed ? 'w-16' : 'w-80'
        }`}
      >
        <div className="flex flex-col h-full glass-light">
          {/* Sidebar Header */}
          <div className="p-4 border-b border-white/5 flex items-center justify-between">
            {!sidebarCollapsed && (
              <div className="flex items-center gap-3 animate-slide-left">
                <div className="relative">
                  <span className="text-2xl block animate-page-turn">📚</span>
                  {/* Sparkle dots */}
                  <span className="absolute -top-1 -right-1 w-2 h-2 animate-sparkle" style={{ animationDelay: '0s' }}>✨</span>
                </div>
                <div>
                  <h1 className="text-xl font-black shimmer-text tracking-tight">BookBot</h1>
                  <p className="text-[10px] text-gray-500 uppercase tracking-widest">Reading Assistant</p>
                </div>
              </div>
            )}
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="p-2 rounded-xl hover:bg-white/8 text-gray-400 hover:text-white transition-all btn-ripple cursor-pointer ml-auto"
              id="sidebar-toggle"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className={`w-4 h-4 transition-transform duration-500 ${sidebarCollapsed ? 'rotate-180' : ''}`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          </div>

          {!sidebarCollapsed && (
            <div className="flex-1 overflow-y-auto p-4 space-y-6 animate-fade-in">
              {/* Book List */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse inline-block" />
                    Your Library
                  </h2>
                  <div className="flex items-center gap-1">
                    {books.length > 0 && (
                      <button
                        onClick={() => setShowClearConfirm(true)}
                        className="p-1.5 rounded-lg hover:bg-red-500/15 text-gray-400 hover:text-red-400 transition-all cursor-pointer btn-ripple"
                        id="clear-library"
                        title="Clear all books & maintain fresh data"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M3 6h18" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          <line x1="10" y1="11" x2="10" y2="17" />
                          <line x1="14" y1="11" x2="14" y2="17" />
                        </svg>
                      </button>
                    )}
                    <button
                      onClick={() => setShowIngest(!showIngest)}
                      className={`p-1.5 rounded-lg transition-all duration-300 cursor-pointer btn-ripple ${
                        showIngest
                          ? 'bg-purple-500/20 text-purple-300 rotate-45'
                          : 'hover:bg-white/5 text-gray-400 hover:text-purple-400'
                      }`}
                      id="toggle-ingest"
                      title="Add a book"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 transition-transform duration-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Ingest Panel */}
                {showIngest && (
                  <div className="mb-4 p-3 rounded-2xl glass border border-purple-500/20 animate-slide-up neon-glow">
                    <h3 className="text-sm font-bold text-purple-300 mb-3 flex items-center gap-2">
                      <span className="animate-float inline-block">➕</span> Add New Book
                    </h3>
                    <BookIngest
                      onIngestText={(data) => handleIngestSuccess(ingestBook, data)}
                      onIngestPdf={(data) => handleIngestSuccess(ingestBookPdf, data)}
                      loading={ingestLoading}
                    />
                  </div>
                )}

                {/* Book Cards */}
                {books.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 text-sm animate-fade-in">
                    <p className="text-4xl mb-3 animate-float inline-block">📖</p>
                    <p className="font-medium">No books yet</p>
                    <p className="text-xs mt-1 text-gray-600">Click + to add your first book</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {books.map((book, i) => (
                      <div
                        key={book.book_id}
                        className={`w-full text-left p-3 rounded-xl transition-all duration-300 group cursor-pointer card-hover btn-ripple relative flex items-start gap-3 ${
                          selectedBook?.book_id === book.book_id
                            ? 'glass-strong border border-purple-500/30 shadow-lg shadow-purple-500/15 neon-glow'
                            : 'hover:bg-white/[0.04] border border-transparent'
                        }`}
                        onClick={() => handleBookSelect(book)}
                        id={`book-${book.book_id}`}
                        style={bookDelayStyles[i] || { animationDelay: `${i * 0.08}s` }}
                      >
                        <span className={`text-xl mt-0.5 transition-all duration-300 ${
                          selectedBook?.book_id === book.book_id ? 'animate-page-turn' : 'group-hover:scale-110 group-hover:rotate-6'
                        }`}>
                          📕
                        </span>
                        <div className="flex-1 min-w-0 pr-1">
                          <h3 className="text-sm font-semibold text-white truncate">{book.title}</h3>
                          <p className="text-xs text-gray-500 truncate">{book.author}</p>
                          <p className="text-[10px] text-gray-600 mt-0.5">{book.total_pages} pages</p>
                        </div>
                        <div className="flex flex-col items-end gap-1.5 shrink-0">
                          {selectedBook?.book_id === book.book_id && (
                            <span className="w-2 h-2 rounded-full bg-purple-400 mt-1 animate-pulse flex-shrink-0" />
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setBookToDelete(book);
                            }}
                            className="p-1 rounded-md text-gray-500 hover:text-red-400 hover:bg-red-500/20 transition-all opacity-40 group-hover:opacity-100 cursor-pointer"
                            title="Remove content & data"
                            id={`delete-book-${book.book_id}`}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M3 6h18" />
                              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Page Controls */}
              {selectedBook && (
                <div className="space-y-4 animate-slide-up">
                  <div className="h-px bg-gradient-to-r from-transparent via-purple-500/30 to-transparent" />
                  <PageSlider
                    currentPage={currentPage}
                    totalPages={selectedBook.total_pages}
                    onPageChange={handlePageChange}
                    disabled={false}
                  />

                  {/* Reading Now Card */}
                  <div className="p-3 rounded-2xl glass border border-white/5 card-hover">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-orange-500 flex items-center justify-center text-[10px] animate-pulse-glow">
                        📖
                      </span>
                      <span className="text-xs font-semibold text-gray-300">Reading Now</span>
                    </div>
                    <p className="text-sm font-bold text-white">{selectedBook.title}</p>
                    <p className="text-xs text-gray-500">{selectedBook.author}</p>
                  </div>

                  <div className="h-px bg-gradient-to-r from-transparent via-orange-500/20 to-transparent" />
                  <StatsDashboard stats={stats} />
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* ── Main Chat Area ───────────────────────────────────────── */}
      <main className="flex-1 flex flex-col relative z-10">
        {/* Top Bar */}
        <header className="px-6 py-3 border-b border-white/5 glass flex items-center justify-between">
          <div className="flex items-center gap-3">
            {selectedBook ? (
              <>
                <span className="text-lg animate-float">💬</span>
                <div>
                  <h2 className="text-sm font-bold text-white">{selectedBook.title}</h2>
                  <p className="text-[10px] text-gray-500">
                    Reading page <span className="text-purple-400 font-bold">{currentPage}</span> of{' '}
                    {selectedBook.total_pages} • Anti-spoiler mode active 🛡️
                  </p>
                </div>
              </>
            ) : (
              <>
                <span className="text-lg animate-float">📚</span>
                <div>
                  <h2 className="text-sm font-semibold text-gray-400">No book selected</h2>
                  <p className="text-[10px] text-gray-600">Choose a book from the sidebar to start chatting</p>
                </div>
              </>
            )}
          </div>

          {/* Right side badges */}
          <div className="flex items-center gap-3">
            {/* Spoiler Shield */}
            {selectedBook && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass border border-green-500/20 animate-slide-right">
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span className="text-[10px] font-bold text-green-400 uppercase tracking-wider">Spoiler Shield On</span>
              </div>
            )}

            {/* Level badge */}
            {stats.level > 1 && (
              <div className={`px-3 py-1.5 rounded-full border border-orange-500/30 glass text-[10px] font-black text-orange-300 animate-slide-right ${levelUpVisible ? 'animate-pulse-glow' : ''}`}>
                ⭐ LVL {stats.level}
              </div>
            )}
          </div>
        </header>

        {/* Main Content Area: Reader + Chat */}
        <div className="flex-1 overflow-hidden relative flex flex-row">
          
          {/* Reader Area (2/3 width) */}
          <div className="flex-[2] flex flex-col relative overflow-hidden">
            <BookReader
              book={selectedBook}
              currentPage={currentPage}
              getPage={getPage}
              loading={false}
              onPageChange={handlePageChange}
            />
          </div>

          {/* Chat Widget Area (1/3 width) */}
          <div className="flex-1 flex flex-col relative overflow-hidden bg-black/40 border-l border-white/5 shadow-2xl">
            {/* Session Quote */}
            {sessionQuote && (
              <div className="relative z-20 animate-slide-up p-4 pb-0 shrink-0">
                <div className="w-full mx-auto p-4 rounded-2xl glass border border-orange-500/15 shadow-2xl relative overflow-hidden group card-hover">
                  <div className="absolute -top-10 -left-10 w-24 h-24 bg-orange-500/10 blur-2xl group-hover:bg-orange-500/20 transition-all duration-700" />
                  <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-purple-500/10 blur-2xl group-hover:bg-purple-500/20 transition-all duration-700" />
                  <p className="text-xs italic text-orange-100/90 leading-relaxed relative z-10">
                    "{sessionQuote.quote}"
                  </p>
                  <div className="mt-2 flex justify-between items-center relative z-10">
                    <span className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">— {selectedBook?.author}</span>
                    <button
                      onClick={() => setSessionQuote(null)}
                      className="text-gray-600 hover:text-gray-300 text-[10px] cursor-pointer transition-colors px-2 py-1 rounded hover:bg-white/5"
                    >
                      Dismiss ✕
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="flex-1 relative overflow-hidden min-h-0">
              <ChatWidget
                onSendMessage={handleSendMessage}
                loading={chatLoading}
                bookSelected={!!selectedBook}
                bookId={selectedBook?.book_id}
                currentPage={currentPage}
                getSuggestions={getSuggestions}
              />
            </div>
          </div>
        </div>

        {/* Error Toast */}
        {error && (
          <div className="absolute bottom-24 left-1/2 -translate-x-1/2 px-4 py-3 rounded-2xl bg-red-500/15 border border-red-500/30 text-red-300 text-sm animate-slide-up z-50 shadow-2xl">
            <div className="flex items-center gap-2">
              <span className="animate-float inline-block">⚠️</span>
              <span>{error}</span>
              <button onClick={clearError} className="ml-2 text-red-400 hover:text-red-200 cursor-pointer transition-colors">✕</button>
            </div>
          </div>
        )}
      </main>

      {/* ── Level-Up Overlay ─────────────────────────────────────── */}
      {levelUpVisible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none animate-fade-in">
          <div className="text-center animate-pop-in">
            <div className="text-7xl mb-2 animate-float">⭐</div>
            <div className="text-4xl font-black shimmer-text">LEVEL UP!</div>
            <div className="text-2xl font-bold text-orange-300 mt-1">Level {stats.level}</div>
            <div className="text-sm text-gray-400 mt-2">Keep reading to grow stronger!</div>
          </div>
        </div>
      )}

      {/* ── New Badge Toast ──────────────────────────────────────── */}
      {newBadge && (
        <div className="fixed bottom-8 right-8 z-50 animate-slide-up">
          <div className="p-4 rounded-2xl glass-strong border border-orange-500/30 shadow-2xl shadow-orange-500/20 flex items-center gap-3 neon-glow">
            <div className="text-3xl animate-badge-unlock">{getBadgeEmoji(newBadge)}</div>
            <div>
              <p className="text-[10px] font-bold text-orange-400 uppercase tracking-widest">Badge Unlocked!</p>
              <p className="text-sm font-bold text-white">{newBadge}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Single Book Removal Modal ───────────────────────────── */}
      {bookToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
          <div className="bg-[#0f0f18] border border-red-500/30 rounded-3xl p-6 max-w-md w-full shadow-2xl animate-pop-in relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-32 h-32 bg-red-500/10 rounded-full blur-2xl pointer-events-none" />
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-2xl bg-red-500/20 text-red-400 flex items-center justify-center text-xl shrink-0">
                🗑️
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Remove Book Content</h3>
                <p className="text-xs text-gray-400">Maintain fresh library data</p>
              </div>
            </div>
            <p className="text-sm text-gray-300 mb-6 leading-relaxed">
              Are you sure you want to remove <span className="text-white font-semibold">"{bookToDelete.title}"</span> and purge all of its page content and vector embeddings?
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setBookToDelete(null)}
                disabled={deleting}
                className="px-4 py-2.5 rounded-xl text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeleteBook}
                disabled={deleting}
                className="px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-500 hover:to-orange-500 shadow-lg shadow-red-600/20 transition-all cursor-pointer flex items-center gap-2"
              >
                {deleting ? 'Removing...' : 'Delete Content & Data'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Clear All Library Data Modal ───────────────────────── */}
      {showClearConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
          <div className="bg-[#0f0f18] border border-red-500/30 rounded-3xl p-6 max-w-md w-full shadow-2xl animate-pop-in relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-32 h-32 bg-red-500/10 rounded-full blur-2xl pointer-events-none" />
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-2xl bg-red-500/20 text-red-400 flex items-center justify-center text-xl shrink-0">
                ⚠️
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Reset BookBot Library</h3>
                <p className="text-xs text-gray-400">Purge all stored content</p>
              </div>
            </div>
            <p className="text-sm text-gray-300 mb-6 leading-relaxed">
              Are you sure you want to clear <span className="text-white font-semibold">ALL books</span> and wipe all vector embeddings and session state from BookBot?
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setShowClearConfirm(false)}
                disabled={deleting}
                className="px-4 py-2.5 rounded-xl text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmClearAll}
                disabled={deleting}
                className="px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-500 hover:to-orange-500 shadow-lg shadow-red-600/20 transition-all cursor-pointer flex items-center gap-2"
              >
                {deleting ? 'Clearing...' : 'Clear All Library Data'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Notification Toast ──────────────────────────────────── */}
      {toastMessage && (
        <div className="fixed bottom-8 left-8 z-50 animate-slide-up">
          <div className="px-4 py-3 rounded-2xl glass-strong border border-purple-500/30 text-white text-xs font-semibold shadow-2xl flex items-center gap-2 neon-glow">
            <span>✨</span>
            <span>{toastMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function getBadgeEmoji(name) {
  const emojis = {
    'First Chapter': '🏁',
    'Night Owl': '🦉',
    'Speed Reader': '⚡',
    'Curious Mind': '🧐',
    'Halfway Hero': '🏆',
    'Bookworm': '🐛',
  };
  return emojis[name] || '🏅';
}

export default App;
