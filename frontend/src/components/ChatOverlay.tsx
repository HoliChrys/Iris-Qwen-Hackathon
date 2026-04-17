/**
 * Chat overlay — pastille bottom-right, opens as floating panel.
 * Wired to Tachikoma backend via useIRISSubscription (SSE + mutations).
 * Auto-detects intent: new report → kanban card, search → graph query.
 */

import { useState, useRef, useEffect } from 'react';
import { useAtom, useAtomValue } from 'jotai';
import { chatOpenAtom, chatMessagesAtom, loadingAtom, connectedAtom } from '@/stores';
import { useIRISSubscription } from '@/hooks/useIRISSubscription';

const EXAMPLE_REPORTS = [
  { q: 'Loan portfolio by branch for last quarter', icon: '🏦' },
  { q: 'Transaction volume by channel this month', icon: '💳' },
  { q: 'Compare branch performance by region', icon: '📊' },
  { q: 'Customer segmentation analysis', icon: '👥' },
  { q: 'Deposit growth rate by account type', icon: '💰' },
  { q: 'NPL ratio trends by product type', icon: '⚠️' },
  { q: 'Cost-income ratio per branch', icon: '📈' },
];

const EXAMPLE_SEARCH = [
  { q: 'Find reports about credit risk', icon: '🔍' },
  { q: 'Search loan portfolio reports from Strategy', icon: '🔎' },
];

export function ChatOverlay() {
  const [open, setOpen] = useAtom(chatOpenAtom);
  const messages = useAtomValue(chatMessagesAtom);
  const loading = useAtomValue(loadingAtom);
  const connected = useAtomValue(connectedAtom);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const { sendMessage, reset, isSending } = useIRISSubscription();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    sendMessage(input.trim());
    setInput('');
  };

  // Pastille (closed)
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-primary shadow-lg flex items-center justify-center hover:scale-105 transition-transform z-50"
      >
        <span className="text-2xl">💬</span>
        {messages.length > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-destructive rounded-full text-[10px] flex items-center justify-center text-white font-bold">
            {messages.filter((m) => m.role === 'assistant').length}
          </span>
        )}
      </button>
    );
  }

  // Panel
  return (
    <div className="fixed bottom-6 right-6 w-[420px] h-[600px] bg-card border border-border rounded-2xl shadow-2xl flex flex-col z-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-[10px] font-bold text-white">AI</div>
          <div>
            <p className="text-sm font-semibold">IRIS Assistant</p>
            <div className="flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-500' : 'bg-muted-foreground'}`} />
              <p className="text-[10px] text-muted-foreground">{connected ? 'Connected' : 'Ready'}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => reset()} className="text-[10px] text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-secondary">Reset</button>
          <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground text-lg px-1">✕</button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="py-4 px-1">
            <p className="text-2xl text-center mb-2">👋</p>
            <p className="text-sm text-foreground text-center">How can I help?</p>
            <p className="text-xs text-muted-foreground text-center mt-1 mb-4">
              Click a query to generate a report
            </p>

            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1">Reports</p>
              {EXAMPLE_REPORTS.map(({ q, icon }) => (
                <button
                  key={q}
                  onClick={() => { sendMessage(q); }}
                  className="w-full text-left flex items-center gap-2 px-2.5 py-2 rounded-lg text-[12px] bg-secondary/50 text-foreground/80 hover:bg-secondary hover:text-foreground transition"
                >
                  <span>{icon}</span>
                  <span>{q}</span>
                </button>
              ))}

              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1 pt-2">Search</p>
              {EXAMPLE_SEARCH.map(({ q, icon }) => (
                <button
                  key={q}
                  onClick={() => { sendMessage(q); }}
                  className="w-full text-left flex items-center gap-2 px-2.5 py-2 rounded-lg text-[12px] bg-blue-500/5 text-foreground/80 hover:bg-blue-500/10 hover:text-foreground transition"
                >
                  <span>{icon}</span>
                  <span>{q}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role !== 'user' && (
              <div className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center text-[9px] font-bold text-white shrink-0 mt-0.5">AI</div>
            )}
            <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
              msg.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-foreground'
            }`}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.intent === 'new_report' && (
                <div className="mt-1.5 flex items-center gap-1 text-[10px] opacity-70">
                  <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
                  Added to Kanban board
                </div>
              )}
            </div>
          </div>
        ))}

        {(loading || isSending) && (
          <div className="flex gap-2">
            <div className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center text-[9px] font-bold text-white shrink-0">AI</div>
            <div className="bg-secondary rounded-xl px-3 py-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSend(); }}
            placeholder="New report or search..."
            className="flex-1 bg-background border border-input rounded-xl px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button onClick={handleSend} disabled={loading || isSending || !input.trim()} className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center disabled:opacity-40">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
