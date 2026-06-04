/**
 * BookBot — ChatWidget component.
 * Premium glassmorphic chat interface with rich animations.
 */

import { useState, useRef, useEffect } from 'react';

export default function ChatWidget({ onSendMessage, loading, bookSelected, bookId, currentPage, getSuggestions }) {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'bot',
      content: '📚 Welcome to BookBot! I\'m your context-aware reading assistant. Select a book and set your current page to get started. Ask me anything about what you\'ve read so far — I\'ll never spoil what\'s ahead!',
      sources: [],
    },
  ]);
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [isFocused, setIsFocused] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load suggestions when book/page changes
  useEffect(() => {
    if (bookSelected && bookId) {
      getSuggestions(bookId, currentPage).then(data => {
        if (data.suggestions) setSuggestions(data.suggestions);
      });
    }
  }, [bookSelected, bookId, currentPage, getSuggestions]);

  const handleSend = async (forcedMessage = null) => {
    const trimmed = forcedMessage || input.trim();
    if (!trimmed || loading) return;

    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      sources: [],
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSuggestions([]);

    try {
      const response = await onSendMessage(trimmed);
      const botMsg = {
        id: `bot-${Date.now()}`,
        role: 'bot',
        content: response.reply,
        sources: response.sources || [],
      };
      setMessages(prev => [...prev, botMsg]);

      if (response.suggestions?.length > 0) {
        setSuggestions(response.suggestions);
      } else {
        const data = await getSuggestions(bookId, currentPage);
        setSuggestions(data.suggestions || []);
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'bot',
          content: `⚠️ Something went wrong: ${err.message}. Please try again.`,
          sources: [],
          isError: true,
        },
      ]);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = input.trim() && bookSelected && !loading;

  return (
    <div className="flex flex-col h-full parchment">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5" id="chat-messages">
        {messages.map((msg, idx) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            style={{ animationDelay: `${idx * 0.03}s` }}
          >
            {/* Bot avatar */}
            {msg.role === 'bot' && (
              <div className="flex-shrink-0 mr-3 mt-1">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-orange-500 flex items-center justify-center text-sm shadow-lg shadow-purple-500/30 animate-pulse-glow">
                  📖
                </div>
              </div>
            )}

            <div
              className={`max-w-[80%] md:max-w-[72%] ${
                msg.role === 'user' ? 'animate-bubble-right' : 'animate-bubble-left'
              }`}
            >
              {/* Bot header */}
              {msg.role === 'bot' && (
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-black text-orange-400 uppercase tracking-widest">
                    Librarian Bot
                  </span>
                </div>
              )}

              {/* Bubble */}
              <div
                className={`rounded-2xl px-4 py-3 shadow-lg transition-all duration-300 ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-br from-purple-600 to-orange-600 text-white rounded-br-md shadow-orange-500/20 hover:shadow-orange-500/40 hover:shadow-xl'
                    : msg.isError
                    ? 'glass border-red-500/30 text-red-300 rounded-bl-md'
                    : 'glass-light rounded-bl-md border-white/5 hover:border-purple-500/20 hover:shadow-purple-500/10 hover:shadow-lg'
                }`}
              >
                {/* Message text */}
                <p className="text-sm leading-relaxed whitespace-pre-wrap font-medium text-slate-200">
                  {msg.content}
                </p>

                {/* Source page badges */}
                {msg.sources?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-white/5">
                    <span className="text-[9px] text-gray-500 self-center font-bold uppercase tracking-tighter">
                      Sources
                    </span>
                    {[...new Set(msg.sources)].sort((a, b) => a - b).map((page) => (
                      <span
                        key={page}
                        className="px-2 py-0.5 text-[9px] font-bold rounded-md bg-purple-500/10 text-purple-300 border border-purple-500/20 animate-pop-in hover:bg-purple-500/20 transition-colors cursor-default"
                      >
                        P.{page}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* User avatar */}
            {msg.role === 'user' && (
              <div className="flex-shrink-0 ml-3 mt-1">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold text-white shadow-lg">
                  U
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div className="flex justify-start animate-fade-in">
            <div className="flex-shrink-0 mr-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-orange-500 flex items-center justify-center text-sm animate-pulse">
                📖
              </div>
            </div>
            <div className="glass-light rounded-2xl rounded-bl-md px-5 py-4 border border-purple-500/10 shadow-lg shadow-purple-500/5">
              <div className="flex gap-2 items-center">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="text-[10px] text-gray-600 ml-1 italic">thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Dynamic Suggestion Chips */}
      {bookSelected && suggestions.length > 0 && (
        <div className="px-4 pb-3 flex gap-2 overflow-x-auto no-scrollbar">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => handleSend(s)}
              className="flex-shrink-0 px-4 py-2 text-xs font-semibold rounded-full glass border border-orange-500/20 text-orange-200/80
                         hover:bg-orange-500/20 hover:border-orange-500/40 hover:text-orange-100
                         hover:shadow-lg hover:shadow-orange-500/10
                         transition-all duration-300 cursor-pointer animate-slide-up btn-ripple"
              style={{ animationDelay: `${i * 0.1}s` }}
            >
              ✨ {s}
            </button>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className={`p-4 border-t transition-all duration-300 ${isFocused ? 'border-purple-500/20 glass' : 'border-white/5 glass'}`}>
        <div className="flex gap-3 items-end max-w-4xl mx-auto">
          <div className="flex-1 relative">
            {/* Glow ring on focus */}
            <div
              className={`absolute inset-0 rounded-2xl transition-all duration-500 pointer-events-none ${
                isFocused
                  ? 'shadow-[0_0_20px_rgba(192,132,252,0.2),0_0_40px_rgba(192,132,252,0.08)]'
                  : 'shadow-none'
              }`}
            />
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={bookSelected ? 'Ask your librarian...' : 'Select a book to start chatting...'}
              disabled={!bookSelected || loading}
              rows={1}
              className="w-full px-5 py-3.5 rounded-2xl glass-light text-sm text-white placeholder-gray-600
                         resize-none focus:outline-none
                         disabled:opacity-40 disabled:cursor-not-allowed
                         transition-all duration-300 shadow-inner relative z-10"
              style={{ minHeight: '52px', maxHeight: '150px' }}
              id="chat-input"
            />
          </div>

          {/* Send Button */}
          <button
            onClick={() => handleSend()}
            disabled={!canSend}
            className={`p-4 rounded-2xl text-white transition-all duration-300 cursor-pointer flex-shrink-0 btn-ripple
              ${canSend
                ? 'bg-gradient-to-br from-purple-600 to-orange-600 hover:from-purple-500 hover:to-orange-500 hover:shadow-xl hover:shadow-orange-500/30 active:scale-90 neon-glow'
                : 'bg-white/5 opacity-30 cursor-not-allowed'
              }`}
            id="send-button"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`w-5 h-5 transition-transform duration-200 ${canSend ? 'hover:translate-x-0.5 hover:-translate-y-0.5' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m22 2-7 20-4-9-9-4Z" />
              <path d="M22 2 11 13" />
            </svg>
          </button>
        </div>

        {/* Keyboard hint */}
        {isFocused && bookSelected && (
          <p className="text-center text-[9px] text-gray-700 mt-2 animate-fade-in">
            Press <kbd className="px-1 py-0.5 rounded bg-white/5 text-gray-600 font-mono">Enter</kbd> to send •{' '}
            <kbd className="px-1 py-0.5 rounded bg-white/5 text-gray-600 font-mono">Shift+Enter</kbd> for new line
          </p>
        )}
      </div>
    </div>
  );
}
