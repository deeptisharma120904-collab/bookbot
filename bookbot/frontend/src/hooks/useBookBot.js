/**
 * BookBot — useBookBot custom hook.
 * Handles all API communication with the FastAPI backend.
 */

import { useState, useCallback } from 'react';

const API_BASE = '/api';

export function useBookBot() {
  const [ingestLoading, setIngestLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState(null);
  const [books, setBooks] = useState([]);
  const [stats, setStats] = useState({
    xp: 0,
    streak: 0,
    badges: [],
    total_pages_read: 0,
    level: 1
  });

  // ─── Ingest a book (JSON text) ──────────────────────────────
  const ingestBook = useCallback(async ({ book_id, title, author, content }) => {
    setIngestLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/books/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id, title, author, content }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Ingestion failed (${res.status})`);
      }
      return await res.json();
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setIngestLoading(false);
    }
  }, []);

  // ─── Ingest a book (PDF upload) ─────────────────────────────
  const ingestBookPdf = useCallback(async (formData) => {
    setIngestLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/books/ingest/pdf`, {
        method: 'POST',
        body: formData, // FormData — no Content-Type header needed
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `PDF ingestion failed (${res.status})`);
      }
      return await res.json();
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setIngestLoading(false);
    }
  }, []);

  // ─── Send a chat message ────────────────────────────────────
  const sendMessage = useCallback(async ({ user_id, book_id, current_page, message, history = [] }) => {
    setChatLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id, book_id, current_page, message, history }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Chat failed (${res.status})`);
      }
      const data = await res.json();
      return data;
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setChatLoading(false);
    }
  }, []);

  // ─── Get session info ───────────────────────────────────────
  const getSession = useCallback(async (userId, bookId) => {
    try {
      const res = await fetch(`${API_BASE}/session/${userId}/${bookId}`);
      if (!res.ok) return null;
      const data = await res.json();
      if (data.stats) setStats(data.stats);
      return data;
    } catch {
      return null;
    }
  }, []);

  // ─── Sync page (webhook simulation) ─────────────────────────
  const syncPage = useCallback(async (userId, bookId, currentPage) => {
    try {
      const res = await fetch(`${API_BASE}/session/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          book_id: bookId,
          current_page: currentPage,
        }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (data.stats) setStats(data.stats);
      return data;
    } catch {
      return null;
    }
  }, []);
  // ─── Get page content ───────────────────────────────────────
  const getPage = useCallback(async (bookId, pageNumber) => {
    try {
      const res = await fetch(`${API_BASE}/books/page/${bookId}/${pageNumber}`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }, []);

  // ─── Get smart suggestions ──────────────────────────────────
  const getSuggestions = useCallback(async (bookId, currentPage) => {
    try {
      const res = await fetch(`${API_BASE}/books/suggestions/${bookId}/${currentPage}`);
      if (!res.ok) return { suggestions: [] };
      return await res.json();
    } catch {
      return { suggestions: [] };
    }
  }, []);

  // ─── Get beautiful quote ──────────────────────────────────
  const getQuote = useCallback(async (bookId, currentPage) => {
    try {
      const res = await fetch(`${API_BASE}/books/quote/${bookId}/${currentPage}`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }, []);

  // ─── List all books ─────────────────────────────────────────
  const listBooks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/books`);
      if (!res.ok) return [];
      const data = await res.json();
      setBooks(data);
      return data;
    } catch {
      return [];
    }
  }, []);

  // ─── Clear error ────────────────────────────────────────────
  const clearError = useCallback(() => setError(null), []);

  return {
    loading: ingestLoading || chatLoading,
    ingestLoading,
    chatLoading,
    error,
    books,
    stats,
    ingestBook,
    ingestBookPdf,
    sendMessage,
    getSession,
    syncPage,
    getSuggestions,
    getQuote,
    getPage,
    listBooks,
    clearError,
  };
}
