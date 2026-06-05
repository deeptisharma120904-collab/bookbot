import React, { useState, useEffect } from 'react';

function BookReader({ book, currentPage, getPage, loading: externalLoading, onPageChange }) {
  const [pageData, setPageData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!book) return;

    const fetchPage = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getPage(book.book_id, currentPage);
        if (data) {
          setPageData(data);
        } else {
          setError('Page content not found.');
          setPageData(null);
        }
      } catch (err) {
        setError('Failed to load page content.');
        setPageData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchPage();
  }, [book, currentPage, getPage]);

  if (!book) {
    return (
      <div className="flex-1 flex items-center justify-center border-r border-white/5 bg-black/20">
        <div className="text-center text-gray-500 animate-fade-in">
          <p className="text-4xl mb-4 animate-float">📖</p>
          <p>Select a book to start reading</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col border-r border-white/5 bg-[#0f0e13] relative overflow-hidden">
      {/* Reader Header */}
      <div className="px-6 py-4 border-b border-white/5 glass flex justify-between items-center shrink-0 z-20">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">{book.title}</h2>
          <p className="text-xs text-gray-500">{book.author}</p>
        </div>
        <div className="flex items-center gap-2">
          {onPageChange && (
            <button 
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage <= 1 || loading || externalLoading}
              className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-gray-300 hover:bg-white/20 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="Previous Page"
            >
              &larr;
            </button>
          )}
          
          <div className="px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs font-semibold text-gray-300 min-w-[100px] text-center">
            Page {currentPage} / {book.total_pages}
          </div>

          {onPageChange && (
            <button 
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage >= book.total_pages || loading || externalLoading}
              className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-gray-300 hover:bg-white/20 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              title="Next Page"
            >
              &rarr;
            </button>
          )}
        </div>
      </div>

      {/* Reader Content - Dark background container */}
      <div className="flex-1 overflow-y-auto relative scroll-smooth flex justify-center items-start py-12 px-4" style={{ perspective: '1000px' }}>
        {(loading || externalLoading) ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
            <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm font-semibold text-purple-300 uppercase tracking-widest animate-pulse">
              Turning Page...
            </p>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <div className="p-6 rounded-2xl bg-red-500/10 border border-red-500/20 text-center">
              <span className="text-3xl mb-2 block">⚠️</span>
              <p className="text-red-300">{error}</p>
            </div>
          </div>
        ) : (
          /* The Physical Page */
          <div 
            className="w-full max-w-2xl bg-[#f4ecd8] shadow-2xl rounded-sm relative transition-all duration-500 animate-fade-in"
            style={{ 
              minHeight: '850px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7), inset 0 0 60px rgba(139, 115, 85, 0.1), -15px 0 30px rgba(0,0,0,0.3)',
              transformOrigin: 'left center',
            }}
          >
            {/* Book Spine Shadow / Crease */}
            <div className="absolute top-0 left-0 bottom-0 w-12 bg-gradient-to-r from-[rgba(0,0,0,0.15)] via-[rgba(0,0,0,0.02)] to-transparent rounded-l-sm z-0 pointer-events-none" />
            
            {/* Subtle paper texture overlay */}
            <div className="absolute inset-0 opacity-[0.4] mix-blend-multiply pointer-events-none" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.65%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E")' }} />

            <div className="relative z-10 px-12 md:px-16 py-20 pb-28 flex flex-col min-h-full">
              {pageData?.page_type === 'cover' ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="w-full max-w-xl mx-auto rounded-[2rem] border border-[#7ab4e4] bg-gradient-to-b from-[#a8d8ff] via-[#7dc0f2] to-[#5f9ed9] px-10 py-14 text-center shadow-[inset_0_0_0_3px_rgba(255,255,255,0.22)]">
                    <div className="mb-8 text-xs uppercase tracking-[0.5em] text-white/80">
                      Book Cover
                    </div>
                    <h3 className="font-serif text-5xl md:text-6xl leading-none text-white drop-shadow-sm">
                      {pageData.title}
                    </h3>
                    <p className="mt-10 text-lg md:text-xl font-semibold uppercase tracking-[0.35em] text-[#234f7e]">
                      {pageData.author}
                    </p>
                    <p className="mt-8 text-sm leading-7 text-[#16324d]/80">
                      {pageData.message}
                    </p>
                  </div>
                </div>
              ) : pageData?.page_type === 'image_only' ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="max-w-lg rounded-3xl border border-amber-900/20 bg-[#f0e2bd] px-8 py-10 text-center text-[#4b3d2d] shadow-xl">
                    <div className="text-4xl mb-4">Illustration</div>
                    <h3 className="font-serif text-3xl">{pageData.title}</h3>
                    <p className="mt-3 text-sm leading-7">{pageData.message}</p>
                  </div>
                </div>
              ) : (
                /* Content text */
                <div className="flex-1 font-serif text-[#2c2826] text-[1.15rem] leading-[1.9] text-justify">
                  {(pageData?.content || '')
                    // Fix PDF hard wrapping:
                    // 1. Standardize newlines
                    .replace(/\r\n/g, '\n')
                    // 2. Identify true paragraphs (separated by blank lines) and replace with placeholder
                    .replace(/\n\s*\n/g, '___PARAGRAPH___')
                    // 3. For any remaining single newlines (hard wrapping), replace with a space
                    .replace(/\n/g, ' ')
                    // 4. Split back into actual paragraphs
                    .split('___PARAGRAPH___')
                    .map((paragraph, index) => {
                      const pText = paragraph.trim();
                      if (!pText) return null;
                      return (
                        <p 
                          key={index} 
                          className={`mb-5 animate-fade-in ${index > 0 ? 'indent-10' : 'first-letter:text-5xl first-letter:font-bold first-letter:mr-1 first-letter:float-left first-letter:text-[#1a1816]'}`} 
                          style={{ animationDelay: `${index * 0.03}s` }}
                        >
                          {pText}
                        </p>
                      );
                    })}
                </div>
              )}

              {/* Page Number on physical page */}
              <div className="absolute bottom-10 left-0 right-0 text-center font-serif text-[#8b7355] text-sm tracking-widest">
                - {currentPage} -
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Outer Decorative gradients for the dark background */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-8 bg-gradient-to-b from-black/60 to-transparent pointer-events-none z-10" />
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full h-12 bg-gradient-to-t from-black/60 to-transparent pointer-events-none z-10" />
    </div>
  );
}

export default BookReader;
