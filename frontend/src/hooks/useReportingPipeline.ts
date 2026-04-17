/**
 * SSE hook for the SB5 reporting pipeline.
 *
 * Connects to the tachikoma backend via:
 *   - POST /api/sb5/action  (init, chat, review)
 *   - GET  /api/events/stream?token=...&channels=... (SSE)
 *
 * Updates Jotai atoms as pipeline steps complete.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useSetAtom, useAtomValue } from 'jotai';
import { useMutation } from '@tanstack/react-query';
import {
  messagesAtom, isLoadingAtom, pipelineStepsAtom,
  reportHtmlAtom, connectedAtom, sessionIdAtom,
} from '@/stores';
import type { ChatMessage, PipelineStep } from '@/types';

const API_BASE = '/api';

export function useReportingPipeline() {
  const setMessages = useSetAtom(messagesAtom);
  const setLoading = useSetAtom(isLoadingAtom);
  const setSteps = useSetAtom(pipelineStepsAtom);
  const setReportHtml = useSetAtom(reportHtmlAtom);
  const setConnected = useSetAtom(connectedAtom);
  const sessionId = useAtomValue(sessionIdAtom);
  const sseRef = useRef<EventSource | null>(null);

  // Init SSE connection
  const connectSSE = useCallback((token: string, channel: string) => {
    if (sseRef.current) sseRef.current.close();

    const url = `${API_BASE}/events/stream?token=${token}&channels=${channel}`;
    const source = new EventSource(url);

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    // Pipeline step events
    source.addEventListener('step.completed', (e) => {
      const data = JSON.parse(e.data);
      setSteps((prev) =>
        prev.map((s) =>
          s.name === data.step_name
            ? { ...s, status: 'done', duration_ms: data.duration_ms, detail: data.detail }
            : s.name === data.next_step
              ? { ...s, status: 'active' }
              : s
        )
      );
    });

    // Agent messages
    source.addEventListener('agent.message', (e) => {
      const data = JSON.parse(e.data);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.content,
          timestamp: new Date().toISOString(),
          pipeline_steps: data.pipeline_steps,
        },
      ]);
    });

    // Report ready
    source.addEventListener('report.ready', (e) => {
      const data = JSON.parse(e.data);
      setReportHtml(data.report_html || '');
      setLoading(false);
    });

    // HITL review request
    source.addEventListener('human_decision', (e) => {
      const data = JSON.parse(e.data);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'system',
          content: 'Review required',
          timestamp: new Date().toISOString(),
          review_request: data,
        },
      ]);
      setSteps((prev) =>
        prev.map((s) => (s.name === 'review' ? { ...s, status: 'active' } : s))
      );
    });

    sseRef.current = source;
  }, [setConnected, setMessages, setSteps, setReportHtml, setLoading]);

  // Cleanup on unmount
  useEffect(() => () => { sseRef.current?.close(); }, []);

  // Send chat message (new report query)
  const sendQuery = useMutation({
    mutationFn: async (query: string) => {
      setLoading(true);
      // Reset pipeline steps
      setSteps((prev) => prev.map((s) => ({ ...s, status: 'pending' as const })));
      // Add user message
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'user', content: query, timestamp: new Date().toISOString() },
      ]);

      const res = await fetch(`${API_BASE}/sb5/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, action: 'chat', message: query }),
      });
      const data = await res.json();

      // Connect SSE if we got a token
      if (data.token && data.channel) {
        connectSSE(data.token, data.channel);
      }

      return data;
    },
  });

  // Submit review decision
  const submitReview = useMutation({
    mutationFn: async (decision: { route: 'approve' | 'revise' | 'reject'; comments?: string; revision_notes?: string }) => {
      const res = await fetch(`${API_BASE}/sb5/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, action: 'review', ...decision }),
      });
      return res.json();
    },
  });

  return { sendQuery, submitReview, connectSSE };
}
