/**
 * Agent Panel — full-page chat with IRIS agent.
 * SSE-driven, example queries, pipeline step indicators.
 */

import { useState, useRef, useEffect } from 'react';
import { useAtomValue } from 'jotai';
import { chatMessagesAtom, loadingAtom, connectedAtom, backendStepAtom } from '@/stores';
import { useIRISSubscription } from '@/hooks/useIRISSubscription';

const QUERIES = [
  { q: 'Loan portfolio by branch Q4', icon: '🏦' },
  { q: 'Transaction volume by channel', icon: '💳' },
  { q: 'Branch performance comparison', icon: '📊' },
  { q: 'NPL ratio trends', icon: '⚠️' },
  { q: 'Customer segmentation', icon: '👥' },
  { q: 'Deposit growth analysis', icon: '💰' },
];

const SEARCH_QUERIES = [
  { q: 'Find reports about credit risk', icon: '⌕' },
  { q: 'Search loan portfolio from Strategy', icon: '⌕' },
];

export function AgentPanel() {
  const messages = useAtomValue(chatMessagesAtom);
  const loading = useAtomValue(loadingAtom);
  const currentStep = useAtomValue(backendStepAtom);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { sendMessage, reset, isSending } = useIRISSubscription();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    sendMessage(input.trim());
    setInput('');
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">

      {/* Header */}
      <div className="h-11 border-b border-[#e8e6e1] bg-[#1a1a2e] flex items-center px-5 gap-3 shrink-0">
        <div className="w-5 h-5 rounded bg-white/10 flex items-center justify-center">
          <span className="text-[10px] text-cyan-400">⬡</span>
        </div>
        <span className="text-[11px] font-medium text-white/80 uppercase tracking-[0.1em]">IRIS Agent</span>
        <div className="flex-1" />

        {currentStep && (
          <div className="flex items-center gap-1.5 bg-white/5 px-2.5 py-0.5 rounded">
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-[10px] text-white/60 font-mono">{currentStep}</span>
          </div>
        )}

        <button
          onClick={() => reset()}
          className="text-[10px] text-white/30 hover:text-white/60 uppercase tracking-wider px-2 py-0.5 rounded hover:bg-white/5 transition"
        >
          Reset
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">

        {/* Empty state */}
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto px-6 py-10">
            <div className="text-center mb-8">
              <div className="w-12 h-12 rounded-lg bg-[#1a1a2e] flex items-center justify-center mx-auto mb-3">
                <span className="text-lg text-cyan-400">⬡</span>
              </div>
              <h3 className="text-[15px] font-semibold text-[#1a1a2e] mb-1">IRIS Agent</h3>
              <p className="text-[12px] text-[#888]">Generate data-driven reports or search existing ones</p>
            </div>

            <div className="space-y-3">
              <p className="text-[10px] font-semibold text-[#999] uppercase tracking-[0.1em]">Generate a report</p>
              <div className="grid grid-cols-2 gap-2">
                {QUERIES.map(({ q, icon }) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="text-left flex items-center gap-2.5 px-3 py-2.5 rounded-md text-[12px] text-[#555] bg-white border border-[#e8e6e1] hover:border-[#ccc] hover:text-[#1a1a2e] hover:shadow-sm transition"
                  >
                    <span>{icon}</span>
                    <span>{q}</span>
                  </button>
                ))}
              </div>

              <p className="text-[10px] font-semibold text-[#999] uppercase tracking-[0.1em] pt-2">Search existing reports</p>
              <div className="flex gap-2">
                {SEARCH_QUERIES.map(({ q, icon }) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="text-left flex items-center gap-2 px-3 py-2 rounded-md text-[12px] text-[#7a6f5f] bg-[#f9f7f2] border border-[#e8e4d9] hover:bg-[#f0ece3] transition"
                  >
                    <span className="opacity-50">{icon}</span>
                    <span>{q}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        {messages.length > 0 && (
          <div className="max-w-2xl mx-auto px-6 py-4 space-y-3">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role !== 'user' && (
                  <div className="w-6 h-6 rounded bg-[#1a1a2e] flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-[9px] text-cyan-400">⬡</span>
                  </div>
                )}
                <div className={`max-w-[80%] rounded-lg px-3 py-2 text-[13px] leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-[#1a1a2e] text-white'
                    : 'bg-white border border-[#e8e6e1] text-[#333]'
                }`}>
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                </div>
              </div>
            ))}

            {(loading || isSending) && (
              <div className="flex gap-2.5">
                <div className="w-6 h-6 rounded bg-[#1a1a2e] flex items-center justify-center shrink-0">
                  <span className="text-[9px] text-cyan-400">⬡</span>
                </div>
                <div className="bg-white border border-[#e8e6e1] rounded-lg px-3 py-2">
                  <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-[#bbb] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-[#bbb] rounded-full animate-bounce" style={{ animationDelay: '100ms' }} />
                    <span className="w-1.5 h-1.5 bg-[#bbb] rounded-full animate-bounce" style={{ animationDelay: '200ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-6 py-3 border-t border-[#e8e6e1] bg-white shrink-0">
        <div className="max-w-2xl mx-auto flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSend(); }}
            placeholder="Ask for a report or search..."
            className="flex-1 bg-[#fafaf8] border border-[#ddd] rounded-md px-3.5 py-2 text-[13px] text-[#333] placeholder:text-[#bbb] focus:outline-none focus:border-[#1a1a2e] focus:ring-1 focus:ring-[#1a1a2e]/10 transition"
          />
          <button
            onClick={handleSend}
            disabled={loading || isSending || !input.trim()}
            className="px-4 py-2 rounded-md bg-[#1a1a2e] text-white text-[12px] font-medium hover:bg-[#2a2a3e] disabled:opacity-30 transition"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
