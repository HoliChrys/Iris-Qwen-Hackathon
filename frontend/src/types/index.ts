/** IRIS — Types for the redesigned UX */

// ─── Report (Kanban card) ───────────────────────────────
export type ReportStatus =
  | 'to_do'
  | 'interpreting'
  | 'fetching'
  | 'generating'
  | 'charting'
  | 'compliance'
  | 'review'        // manual validation
  | 'published'
  | 'rejected';

export interface ReportCard {
  id: string;
  title: string;
  query_text: string;
  department: string;
  requester: string;
  report_type: string;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  status: ReportStatus;
  chart_count: number;
  compliance_score: number;
  tags: string[];
  created_at: string;
  updated_at: string;
  folder_path?: string;       // TreeFile location after publish
  version?: number;           // for recurring reports
  html_preview?: string;
}

export const KANBAN_COLUMNS: { status: ReportStatus; label: string; color: string }[] = [
  { status: 'to_do',         label: 'To Do',        color: 'bg-slate-500' },
  { status: 'interpreting',  label: 'Interpreting',  color: 'bg-blue-500' },
  { status: 'fetching',      label: 'Fetching Data', color: 'bg-cyan-500' },
  { status: 'generating',    label: 'Generating',    color: 'bg-violet-500' },
  { status: 'charting',      label: 'Charts',        color: 'bg-purple-500' },
  { status: 'compliance',    label: 'Compliance',    color: 'bg-amber-500' },
  { status: 'review',        label: 'Review',        color: 'bg-orange-500' },
  { status: 'published',     label: 'Published',     color: 'bg-green-500' },
];

// ─── TreeFile ───────────────────────────────────────────
export interface TreeNode {
  id: string;
  name: string;
  type: 'folder' | 'report';
  children?: TreeNode[];
  tags?: string[];
  report_id?: string;         // if type === 'report'
  version_count?: number;     // history count for recurring
  icon?: string;
}

// ─── Data Source ─────────────────────────────────────────
export interface DataSource {
  id: string;
  name: string;
  type: 'kafka_topic' | 'clickhouse_table' | 'webhook' | 'api';
  endpoint: string;           // webhook URL or topic name
  status: 'active' | 'paused' | 'error';
  events_count: number;
  last_event_at?: string;
  bound_agents: string[];     // agent names hooked to this source
}

// ─── Chat ───────────────────────────────────────────────
export type ChatIntent = 'new_report' | 'search' | 'question' | 'unknown';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  intent?: ChatIntent;
  report_id?: string;         // linked kanban card
  search_results?: SearchResult[];
}

export interface SearchResult {
  id: string;
  source: 'neo4j' | 'clickhouse' | 'graphiti';
  title: string;
  department: string;
  report_type: string;
  status: string;
  tags: string[];
  score?: number;
}

// ─── Pipeline step (for Kanban card detail) ─────────────
export interface PipelineStep {
  name: string;
  label: string;
  status: 'pending' | 'active' | 'done' | 'error';
  duration_ms?: number;
}
