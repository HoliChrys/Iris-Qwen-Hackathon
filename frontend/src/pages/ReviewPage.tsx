/**
 * Review queue — pending HITL reports awaiting approval.
 */

export function ReviewPage() {
  const pendingReports = [
    { id: 'rpt-001', title: 'Portefeuille de Prêts Q4 2025', dept: 'Strategy Division', type: 'loan_portfolio', charts: 3, score: 1.0, time: '2 min ago' },
    { id: 'rpt-002', title: 'Volume Transactions par Canal', dept: 'ICT - Reporting', type: 'daily_summary', charts: 2, score: 0.8, time: '5 min ago' },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h2 className="text-lg font-semibold mb-1">Pending Review</h2>
      <p className="text-sm text-muted-foreground mb-5">{pendingReports.length} reports awaiting human review</p>

      <div className="space-y-3">
        {pendingReports.map((r) => (
          <div key={r.id} className="bg-card border border-sb5-amber/30 rounded-xl p-5 flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-sb5-amber/10 flex items-center justify-center text-lg">📄</div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold">{r.title}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{r.dept} · {r.type} · {r.charts} charts</p>
              <div className="flex gap-1.5 mt-2">
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${r.score >= 0.9 ? 'bg-sb5-green/20 text-sb5-green' : 'bg-sb5-amber/20 text-sb5-amber'}`}>
                  Compliance: {(r.score * 100).toFixed(0)}%
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">{r.time}</span>
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button className="px-3 py-1.5 rounded-lg text-xs font-medium bg-sb5-green text-white hover:opacity-90">Approve</button>
              <button className="px-3 py-1.5 rounded-lg text-xs font-medium bg-sb5-amber text-black hover:opacity-90">Revise</button>
              <button className="px-3 py-1.5 rounded-lg text-xs font-medium bg-sb5-red text-white hover:opacity-90">Reject</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
