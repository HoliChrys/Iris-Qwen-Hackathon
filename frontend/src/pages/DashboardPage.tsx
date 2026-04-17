/**
 * Dashboard page — KPIs + charts from ClickHouse views.
 */

import { useQuery } from '@tanstack/react-query';

interface KPI { label: string; value: string; sub?: string; color?: string }

const KPIS: KPI[] = [
  { label: 'Total Loans Disbursed', value: '16,581M', sub: 'All branches, all periods' },
  { label: 'Total Deposits', value: '25,903M', sub: '4 account types' },
  { label: 'Transaction Volume', value: '32.5M', sub: '4 channels' },
  { label: 'Total Customers', value: '16.1M', sub: '4 segments' },
  { label: 'Avg NPL Ratio', value: '4.73%', color: 'text-sb5-amber' },
  { label: 'Efficiency Score', value: '74.6%', color: 'text-sb5-green' },
  { label: 'Reports Published', value: '9', color: 'text-accent' },
];

function KPICard({ label, value, sub, color }: KPI) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 text-center">
      <p className={`text-2xl font-bold ${color || 'text-accent'}`}>{value}</p>
      <p className="text-[11px] text-muted-foreground uppercase tracking-wider mt-1">{label}</p>
      {sub && <p className="text-[10px] text-muted-foreground/60 mt-0.5">{sub}</p>}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-3 text-foreground">{title}</h3>
      <div className="h-[200px] bg-background rounded-lg flex items-center justify-center text-muted-foreground text-xs">
        {children || 'Chart — loads from ClickHouse view'}
      </div>
    </div>
  );
}

export function DashboardPage() {
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h2 className="text-lg font-semibold mb-5">Dashboard — ClickHouse DWH Overview</h2>

      {/* KPIs */}
      <div className="grid grid-cols-7 gap-3 mb-6">
        {KPIS.map((k) => <KPICard key={k.label} {...k} />)}
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <ChartCard title="📊 Loan Portfolio by Branch">
          <p>SELECT * FROM dwh.v_loans_by_branch</p>
        </ChartCard>
        <ChartCard title="📉 NPL Ratio by Branch">
          <p>SELECT * FROM dwh.v_loans_by_branch</p>
        </ChartCard>
        <ChartCard title="📈 Loans Trend by Period">
          <p>SELECT * FROM dwh.v_loans_by_period</p>
        </ChartCard>
        <ChartCard title="🏦 Deposits by Account Type">
          <p>SELECT * FROM dwh.v_deposits_by_type</p>
        </ChartCard>
        <ChartCard title="💳 Transactions by Channel">
          <p>SELECT * FROM dwh.v_transactions_by_channel</p>
        </ChartCard>
        <ChartCard title="🏢 Branch Profitability">
          <p>SELECT * FROM dwh.v_branch_performance</p>
        </ChartCard>
      </div>

      {/* Tables */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">👥 Customer Segments</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 text-muted-foreground">Segment</th>
                <th className="text-right py-2 text-muted-foreground">Customers</th>
                <th className="text-right py-2 text-muted-foreground">Churn %</th>
              </tr>
            </thead>
            <tbody>
              {[
                { s: 'Corporate', c: '4.2M', ch: '4.82%' },
                { s: 'Premium', c: '4.1M', ch: '5.01%' },
                { s: 'Retail', c: '4.0M', ch: '4.95%' },
                { s: 'SME', c: '3.9M', ch: '5.11%' },
              ].map((r) => (
                <tr key={r.s} className="border-b border-border/50">
                  <td className="py-2">{r.s}</td>
                  <td className="py-2 text-right">{r.c}</td>
                  <td className="py-2 text-right">{r.ch}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">🏢 Branch Performance</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 text-muted-foreground">Branch</th>
                <th className="text-right py-2 text-muted-foreground">Profit (M)</th>
                <th className="text-right py-2 text-muted-foreground">Efficiency</th>
              </tr>
            </thead>
            <tbody>
              {[
                { b: 'Branch-D', p: '5.12', e: '75.3%' },
                { b: 'Branch-A', p: '5.08', e: '74.1%' },
                { b: 'Branch-C', p: '4.95', e: '73.8%' },
                { b: 'HQ', p: '4.87', e: '76.2%' },
              ].map((r) => (
                <tr key={r.b} className="border-b border-border/50">
                  <td className="py-2">{r.b}</td>
                  <td className="py-2 text-right">{r.p}</td>
                  <td className="py-2 text-right">{r.e}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
