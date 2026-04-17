/**
 * Kanban board — reports flow through Hive status columns.
 * Maps directly to the pipeline branching (like CRM example).
 */

import { useAtom, useSetAtom } from 'jotai';
import { reportsAtom, selectedReportAtom, reportDetailOpenAtom } from '@/stores';
import { KANBAN_COLUMNS, type ReportCard, type ReportStatus } from '@/types';

function Card({ report }: { report: ReportCard }) {
  const setSelected = useSetAtom(selectedReportAtom);
  const setDetailOpen = useSetAtom(reportDetailOpenAtom);

  const priorityColor: Record<string, string> = {
    urgent: 'border-l-red-500',
    high: 'border-l-orange-500',
    normal: 'border-l-blue-500',
    low: 'border-l-slate-400',
  };

  return (
    <div
      onClick={() => { setSelected(report); setDetailOpen(true); }}
      className={`bg-card border border-border rounded-lg p-3 cursor-pointer hover:ring-1 hover:ring-ring/30 transition border-l-2 ${priorityColor[report.priority] || ''}`}
    >
      <p className="text-xs font-semibold truncate">{report.title || report.query_text.slice(0, 50)}</p>
      <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{report.department}</p>

      <div className="flex flex-wrap gap-1 mt-2">
        {report.tags.slice(0, 3).map((t) => (
          <span key={t} className="px-1.5 py-0.5 rounded text-[9px] bg-secondary text-muted-foreground">{t}</span>
        ))}
      </div>

      <div className="flex items-center justify-between mt-2">
        <span className="text-[10px] text-muted-foreground">{report.requester}</span>
        <div className="flex gap-1.5">
          {report.chart_count > 0 && <span className="text-[10px] text-muted-foreground">📊 {report.chart_count}</span>}
          {report.compliance_score > 0 && (
            <span className={`text-[10px] ${report.compliance_score >= 0.9 ? 'text-green-500' : 'text-amber-500'}`}>
              {(report.compliance_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function Column({ status, label, color }: { status: ReportStatus; label: string; color: string }) {
  const [reports] = useAtom(reportsAtom);
  const cards = reports.filter((r) => r.status === status);

  return (
    <div className="flex-1 min-w-[180px] max-w-[220px]">
      {/* Column header */}
      <div className="flex items-center gap-2 mb-3 px-1">
        <div className={`w-2 h-2 rounded-full ${color}`} />
        <span className="text-xs font-semibold">{label}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{cards.length}</span>
      </div>

      {/* Cards */}
      <div className="space-y-2">
        {cards.map((r) => <Card key={r.id} report={r} />)}
        {cards.length === 0 && (
          <div className="border border-dashed border-border rounded-lg p-4 text-center">
            <p className="text-[10px] text-muted-foreground">No reports</p>
          </div>
        )}
      </div>
    </div>
  );
}

export function KanbanBoard() {
  return (
    <div className="flex-1 overflow-x-auto p-5">
      <div className="flex gap-3 min-w-max">
        {KANBAN_COLUMNS.map((col) => (
          <Column key={col.status} {...col} />
        ))}
      </div>
    </div>
  );
}
