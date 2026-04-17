import { useState } from 'react';
import { useReportingPipeline } from '@/hooks/useReportingPipeline';
import type { ReviewRequest } from '@/types';

interface Props {
  review: ReviewRequest;
}

export function ReviewCard({ review }: Props) {
  const [notes, setNotes] = useState('');
  const { submitReview } = useReportingPipeline();

  return (
    <div className="border border-sb5-amber rounded-xl p-4 mt-2.5 bg-sb5-amber/5">
      <h4 className="text-sb5-amber text-sm font-semibold flex items-center gap-1.5 mb-2.5">
        ⚠️ Human Review Required
      </h4>

      <p className="text-sm font-medium mb-2">📄 {review.report_title}</p>

      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className="bg-secondary px-2 py-0.5 rounded-full text-[11px] text-muted-foreground">
          {review.report_type}
        </span>
        <span className="bg-secondary px-2 py-0.5 rounded-full text-[11px] text-muted-foreground">
          Compliance: {review.compliance_passed ? '✅ PASS' : '❌ FAIL'} ({(review.compliance_score * 100).toFixed(0)}%)
        </span>
        <span className="bg-secondary px-2 py-0.5 rounded-full text-[11px] text-muted-foreground">
          {review.charts.length} charts
        </span>
        <span className="bg-secondary px-2 py-0.5 rounded-full text-[11px] text-muted-foreground">
          {review.data_rows} data rows
        </span>
      </div>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Revision notes (optional)..."
        className="w-full bg-background border border-input rounded-lg p-2 text-sm text-foreground placeholder:text-muted-foreground resize-y min-h-[56px] mb-3"
      />

      <div className="flex gap-2">
        <button
          onClick={() => submitReview.mutate({ route: 'approve', comments: notes })}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-sb5-green text-white hover:opacity-90 transition"
        >
          ✓ Approve & Publish
        </button>
        <button
          onClick={() => submitReview.mutate({ route: 'revise', revision_notes: notes })}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-sb5-amber text-black hover:opacity-90 transition"
        >
          ↻ Request Revision
        </button>
        <button
          onClick={() => submitReview.mutate({ route: 'reject', comments: notes })}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-sb5-red text-white hover:opacity-90 transition"
        >
          ✗ Reject
        </button>
      </div>
    </div>
  );
}
