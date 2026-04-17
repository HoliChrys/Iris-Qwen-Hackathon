import { useAtom } from 'jotai';
import { activePageAtom, type Page } from '@/stores';

const NAV_ITEMS: { page: Page; label: string; icon: string; badge?: number }[] = [
  { page: 'chat', label: 'New Report', icon: '💬' },
  { page: 'search', label: 'Search Reports', icon: '🔍' },
  { page: 'dashboard', label: 'Dashboard', icon: '📊' },
  { page: 'review', label: 'Pending Review', icon: '⏳', badge: 2 },
  { page: 'history', label: 'History', icon: '📋' },
  { page: 'data', label: 'Data Explorer', icon: '🗄️' },
];

export function Sidebar() {
  const [activePage, setActivePage] = useAtom(activePageAtom);

  return (
    <aside className="w-[260px] bg-card border-r border-border flex flex-col h-screen">
      {/* Header */}
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white">
            BI
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">SB5 Reports</h1>
            <p className="text-[10px] text-muted-foreground">AI-Powered BI Automation</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-0.5">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-3 pt-2 pb-1">
          Main
        </p>
        {NAV_ITEMS.map(({ page, label, icon, badge }) => (
          <button
            key={page}
            onClick={() => setActivePage(page)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
              activePage === page
                ? 'bg-accent/20 text-accent'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
            }`}
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
            {badge && (
              <span className="ml-auto bg-destructive text-destructive-foreground text-[10px] px-1.5 py-0.5 rounded-full">
                {badge}
              </span>
            )}
          </button>
        ))}

        <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-3 pt-4 pb-1">
          Data Domains
        </p>
        {['Loans', 'Deposits', 'Transactions', 'Customers', 'Branches'].map((d) => (
          <button
            key={d}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <span className="text-base">📁</span>
            <span>{d}</span>
          </button>
        ))}
      </nav>

      {/* User */}
      <div className="p-4 border-t border-border flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-xs font-semibold text-primary-foreground">
          MA
        </div>
        <div>
          <p className="text-xs font-medium">Mohamed A.</p>
          <p className="text-[10px] text-muted-foreground">Strategy Division</p>
        </div>
      </div>
    </aside>
  );
}
