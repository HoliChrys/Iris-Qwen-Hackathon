/** IRIS — Jotai atoms (event-driven, synced via SSE) */

import { atom } from 'jotai';
import type { ReportCard, TreeNode, DataSource, ChatMessage } from '@/types';

// ─── Session ───────────────────────────────────────────────
const SESSION_KEY = 'tachikoma-iris-session';
function getOrCreateSessionId(): string {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const id = `iris-${crypto.randomUUID().slice(0, 12)}`;
  sessionStorage.setItem(SESSION_KEY, id);
  return id;
}
export const sessionIdAtom = atom(getOrCreateSessionId());

// ─── SSE connection ────────────────────────────────────────
export const connectedAtom = atom(false);
export const loadingAtom = atom(false);

// ─── Chat overlay ──────────────────────────────────────────
export const chatOpenAtom = atom(false);
export const chatMessagesAtom = atom<ChatMessage[]>([]);

// ─── Pipeline state (from SSE) ─────────────────────────────
export const backendStepAtom = atom<string>('');
export const reportHtmlAtom = atom('');

// ─── Kanban ────────────────────────────────────────────────
export const reportsAtom = atom<ReportCard[]>([]);
export const selectedReportAtom = atom<ReportCard | null>(null);
export const reportDetailOpenAtom = atom(false);

// ─── TreeFile ──────────────────────────────────────────────
export const treeAtom = atom<TreeNode[]>([
  {
    id: 'root-loans', name: 'Loan Reports', type: 'folder', tags: ['loans'], children: [
      { id: 'f-portfolio', name: 'Portfolio Analysis', type: 'folder', tags: ['portfolio'], children: [] },
      { id: 'f-npl', name: 'NPL Monitoring', type: 'folder', tags: ['npl', 'risk'], children: [] },
    ],
  },
  {
    id: 'root-tx', name: 'Transaction Reports', type: 'folder', tags: ['transactions'], children: [
      { id: 'f-channels', name: 'By Channel', type: 'folder', tags: ['channel'], children: [] },
    ],
  },
  { id: 'root-branches', name: 'Branch Performance', type: 'folder', tags: ['branches'], children: [] },
  { id: 'root-customers', name: 'Customer Analytics', type: 'folder', tags: ['customers'], children: [] },
]);
export const selectedTreeNodeAtom = atom<string | null>(null);

// ─── Data Sources ──────────────────────────────────────────
export const dataSourcesAtom = atom<DataSource[]>([
  { id: 'ds-loans', name: 'dwh.fact_loans', type: 'clickhouse_table', endpoint: 'dwh.fact_loans', status: 'active', events_count: 640, bound_agents: ['query_interpreter'] },
  { id: 'ds-deposits', name: 'dwh.fact_deposits', type: 'clickhouse_table', endpoint: 'dwh.fact_deposits', status: 'active', events_count: 640, bound_agents: [] },
  { id: 'ds-tx', name: 'dwh.fact_transactions', type: 'clickhouse_table', endpoint: 'dwh.fact_transactions', status: 'active', events_count: 640, bound_agents: [] },
  { id: 'ds-kafka', name: 'sb5.report.requests', type: 'kafka_topic', endpoint: 'sb5.report.requests', status: 'active', events_count: 5, bound_agents: ['pipeline'] },
  { id: 'ds-events', name: 'sb5.report.events', type: 'kafka_topic', endpoint: 'sb5.report.events', status: 'active', events_count: 5, bound_agents: [] },
]);
export const addSourceDialogAtom = atom(false);

// ─── Active view ───────────────────────────────────────────
export type MainView = 'kanban' | 'report_detail' | 'data_sources';
export const mainViewAtom = atom<MainView>('kanban');
