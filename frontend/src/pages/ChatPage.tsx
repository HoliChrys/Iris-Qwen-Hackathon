/**
 * Chat + Report Preview split view.
 * Left: conversational chat with pipeline status + HITL review.
 * Right: live report preview with tabs (Report, Data, XML, Charts, Graph).
 */

import { useState, useRef, useEffect } from 'react';
import { useAtomValue } from 'jotai';
import { messagesAtom, isLoadingAtom, reportHtmlAtom } from '@/stores';
import { useReportingPipeline } from '@/hooks/useReportingPipeline';
import { PipelineStatus } from '@/components/PipelineStatus';
import { ReviewCard } from '@/components/ReviewCard';

export function ChatPage() {
  const [input, setInput] = useState('');
  const messages = useAtomValue(messagesAtom);
  const isLoading = useAtomValue(isLoadingAtom);
  const reportHtml = useAtomValue(reportHtmlAtom);
  const { sendQuery } = useReportingPipeline();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [previewTab, setPreviewTab] = useState<'report' | 'data' | 'xml' | 'charts' | 'graph'>('report');

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    sendQuery.mutate(input.trim());
    setInput('');
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* ═══ LEFT: Chat Panel ═══ */}
      <div className="w-1/2 border-r border-border flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Welcome */}
          {messages.length === 0 && (
            <div className="flex gap-2.5">
              <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center text-[10px] font-bold text-white shrink-0">AI</div>
              <div>
                <p className="text-[11px] text-muted-foreground mb-1">AI Reporting Assistant</p>
                <p className="text-sm text-foreground/80 leading-relaxed">
                  Bonjour ! Posez-moi une question sur vos données bancaires et je générerai un rapport complet avec des visualisations.
                </p>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {['loans', 'deposits', 'transactions', 'customers', 'branches'].map((d) => (
                    <span key={d} className="bg-secondary px-2 py-0.5 rounded text-[11px] text-muted-foreground font-mono">{d}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg) => (
            <div key={msg.id} className="flex gap-2.5">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0 ${
                msg.role === 'user' ? 'bg-blue-500' : msg.role === 'assistant' ? 'bg-purple-600' : 'bg-muted-foreground'
              }`}>
                {msg.role === 'user' ? 'MA' : msg.role === 'assistant' ? 'AI' : '⚠'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-muted-foreground mb-0.5">
                  {msg.role === 'user' ? 'You' : msg.role === 'assistant' ? 'AI Pipeline' : 'System'}
                </p>
                <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                {msg.pipeline_steps && <PipelineStatus />}
                {msg.review_request && <ReviewCard review={msg.review_request} />}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-2.5">
              <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center text-[10px] font-bold text-white shrink-0">AI</div>
              <div>
                <p className="text-[11px] text-muted-foreground mb-1">AI Pipeline</p>
                <p className="text-sm text-muted-foreground">Processing your request...</p>
                <PipelineStatus />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-border bg-card">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Posez votre question sur les données bancaires..."
              className="flex-1 bg-background border border-input rounded-xl px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground resize-none h-[42px] focus:outline-none focus:ring-1 focus:ring-ring"
              rows={1}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="w-[42px] h-[42px] bg-sb5-green rounded-xl flex items-center justify-center hover:opacity-90 transition disabled:opacity-40"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            </button>
          </div>
        </div>
      </div>

      {/* ═══ RIGHT: Preview Panel ═══ */}
      <div className="w-1/2 flex flex-col bg-background">
        {/* Tabs */}
        <div className="flex border-b border-border bg-card">
          {(['report', 'data', 'xml', 'charts', 'graph'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setPreviewTab(tab)}
              className={`px-5 py-3 text-sm capitalize border-b-2 transition-colors ${
                previewTab === tab
                  ? 'text-accent border-accent'
                  : 'text-muted-foreground border-transparent hover:text-foreground'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Preview content */}
        <div className="flex-1 overflow-y-auto p-5">
          {previewTab === 'report' && (
            reportHtml ? (
              <div
                className="bg-white rounded-lg shadow-sm"
                dangerouslySetInnerHTML={{ __html: reportHtml }}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                <div className="text-center">
                  <p className="text-4xl mb-3">📄</p>
                  <p>Report preview will appear here</p>
                  <p className="text-xs mt-1">Submit a query to generate a report</p>
                </div>
              </div>
            )
          )}
          {previewTab === 'data' && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              <div className="text-center">
                <p className="text-4xl mb-3">📊</p>
                <p>Raw data from ClickHouse</p>
              </div>
            </div>
          )}
          {previewTab === 'xml' && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              <div className="text-center">
                <p className="text-4xl mb-3">📝</p>
                <p>XML report source</p>
              </div>
            </div>
          )}
          {previewTab === 'charts' && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              <div className="text-center">
                <p className="text-4xl mb-3">📈</p>
                <p>Individual chart previews</p>
              </div>
            </div>
          )}
          {previewTab === 'graph' && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              <div className="text-center">
                <p className="text-4xl mb-3">🔗</p>
                <p>Neo4j entity graph</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
