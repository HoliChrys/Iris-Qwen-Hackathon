/**
 * IRIS SSE Subscription — connects to Tachikoma backend via TracedView + TracedSSEView.
 *
 * Same pattern as booking example:
 * - POST /api/iris/action → {action: init|chat|reset, session_id, message}
 * - SSE  /api/iris/events?token=...&channels=iris.{session_id}
 */

import { useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useSetAtom, useAtomValue } from 'jotai';
import {
  chatMessagesAtom, loadingAtom, connectedAtom, sessionIdAtom,
  backendStepAtom, reportHtmlAtom, reportsAtom,
} from '@/stores';
import type { ChatMessage, ReportCard } from '@/types';

// Relative — vite proxy forwards to Ray Serve (localhost:8000)
const API_BASE = '';

// ── API calls ───────────────────────────────────────────────

async function postAction(sessionId: string, action: string, extra: Record<string, any> = {}) {
  const res = await fetch(`${API_BASE}/api/iris/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, action, ...extra }),
  });
  return res.json();
}

// ── Step name → Kanban status mapping ───────────────────────

const STEP_TO_STATUS: Record<string, string> = {
  interpret_query: 'interpreting',
  interpret: 'interpreting',
  fetch_data: 'fetching',
  fetch: 'fetching',
  generate_report: 'generating',
  generate: 'generating',
  render_charts: 'charting',
  charts: 'charting',
  check_compliance: 'compliance',
  compliance: 'compliance',
  human_review: 'review',
  review: 'review',
  publish: 'published',
};

// ── Hook ────────────────────────────────────────────────────

export function useIRISSubscription() {
  const sseRef = useRef<EventSource | null>(null);

  const sessionId = useAtomValue(sessionIdAtom);
  const setMessages = useSetAtom(chatMessagesAtom);
  const setLoading = useSetAtom(loadingAtom);
  const setConnected = useSetAtom(connectedAtom);
  const setBackendStep = useSetAtom(backendStepAtom);
  const setReportHtml = useSetAtom(reportHtmlAtom);
  const setReports = useSetAtom(reportsAtom);

  // ── SSE connection ────────────────────────────────────────

  const connectSSE = useCallback((token: string, channel: string) => {
    if (sseRef.current) sseRef.current.close();

    const url = `${API_BASE}/api/iris/events?token=${encodeURIComponent(token)}&channels=${encodeURIComponent(channel)}`;
    const source = new EventSource(url);
    sseRef.current = source;

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    // Agent message
    source.addEventListener('agent.message', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const content = data.content || data.payload?.content || '';
        if (content) {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && last.content === content) return prev;
            return [...prev, {
              id: crypto.randomUUID(),
              role: 'assistant',
              content,
              timestamp: new Date().toISOString(),
            }];
          });
          setLoading(false);
        }
      } catch { /* ignore */ }
    });

    // Step completed
    source.addEventListener('step.completed', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const payload = data.payload || data;
        const stepName = payload.step_name || payload.step || '';
        const kanbanStatus = STEP_TO_STATUS[stepName];
        if (stepName) setBackendStep(stepName);
        if (kanbanStatus) {
          setReports((prev) => {
            const last = prev[prev.length - 1];
            if (!last) return prev;
            return prev.map((r) =>
              r.id === last.id ? { ...r, status: kanbanStatus as any, updated_at: new Date().toISOString() } : r
            );
          });
        }
      } catch { /* ignore */ }
    });

    // Report ready
    source.addEventListener('report.ready', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.report_html) {
          setReportHtml(data.report_html);
          setReports((prev) => {
            const last = prev[prev.length - 1];
            if (!last) return prev;
            return prev.map((r) =>
              r.id === last.id ? { ...r, status: 'published' as any, html_preview: data.report_html } : r
            );
          });
        }
        setLoading(false);
      } catch { /* ignore */ }
    });

    // Journal events (native tachikoma SSE)
    source.addEventListener('journal.transition', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.to_state) setBackendStep(data.to_state);
      } catch { /* ignore */ }
    });

    source.addEventListener('journal.update', (e: MessageEvent) => {
      // Field updates from backend
    });

    source.addEventListener('component.stack', (e: MessageEvent) => {
      // UI component updates
    });

    source.addEventListener('wot.graph', (e: MessageEvent) => {
      // WOT topology updates
    });
  }, [setConnected, setMessages, setLoading, setBackendStep, setReportHtml, setReports]);

  useEffect(() => () => { sseRef.current?.close(); }, []);

  // ── Response handler ──────────────────────────────────────

  const handleResponse = useCallback((data: any) => {
    // Agent message from HTTP response
    if (data.agent_message) {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === 'assistant' && last.content === data.agent_message) return prev;
        return [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.agent_message,
          timestamp: new Date().toISOString(),
        }];
      });
    }

    // Connect SSE
    if (data.token && data.channel) {
      connectSSE(data.token, data.channel);
    }

    setLoading(false);
  }, [connectSSE, setMessages, setLoading]);

  // ── Chat mutation ─────────────────────────────────────────

  const chatMutation = useMutation({
    mutationFn: (message: string) => postAction(sessionId, 'chat', { message }),
    onMutate: (message) => {
      setMessages((prev) => [...prev, {
        id: crypto.randomUUID(),
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      }]);
      setLoading(true);

      // Create kanban card for report queries
      const isSearch = /search|find|cherche|trouv/i.test(message);
      if (!isSearch) {
        setReports((prev) => [...prev, {
          id: crypto.randomUUID().slice(0, 8),
          title: message.slice(0, 60),
          query_text: message,
          department: 'User',
          requester: 'You',
          report_type: 'general',
          priority: 'normal' as const,
          status: 'to_do' as const,
          chart_count: 0,
          compliance_score: 0,
          tags: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }]);
      }
    },
    onSuccess: handleResponse,
    onError: () => setLoading(false),
  });

  // ── Reset ─────────────────────────────────────────────────

  const resetMutation = useMutation({
    mutationFn: () => postAction(sessionId, 'reset'),
    onMutate: () => {
      setMessages([]);
      setReportHtml('');
      setBackendStep('');
      setReports([]);
      setLoading(false);
    },
    onSuccess: handleResponse,
  });

  return {
    sessionId,
    sendMessage: chatMutation.mutate,
    reset: resetMutation.mutate,
    isSending: chatMutation.isPending,
  };
}
