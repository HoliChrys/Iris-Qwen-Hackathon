/**
 * IRIS — Intelligent Reporting & Insight System
 *
 * Sidebar: Nav buttons (Agent/Status) + TreeFile + DataSources
 * Main: switches between Agent chat and Kanban board
 */

import { useState } from 'react';
import { useAtomValue } from 'jotai';
import { connectedAtom, reportsAtom } from '@/stores';
import { TreeFile } from '@/components/TreeFile';
import { DataSources, AddSourceDialog } from '@/components/DataSources';
import { KanbanBoard } from '@/components/KanbanBoard';
import { AgentPanel } from '@/components/AgentPanel';

type View = 'agent' | 'status';

export function App() {
  const [view, setView] = useState<View>('agent');
  const connected = useAtomValue(connectedAtom);
  const reports = useAtomValue(reportsAtom);

  return (
    <div className="flex h-screen overflow-hidden bg-[#fafaf8]">

      {/* ═══ LEFT SIDEBAR ═══ */}
      <aside className="w-[220px] bg-white border-r border-[#e8e6e1] flex flex-col shrink-0">

        {/* Logo */}
        <div className="px-4 py-4 border-b border-[#e8e6e1]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#1a1a2e] flex items-center justify-center">
              <span className="text-[10px] font-bold text-white tracking-[0.15em]">IR</span>
            </div>
            <div>
              <h1 className="text-[13px] font-semibold text-[#1a1a2e] tracking-tight leading-none">IRIS</h1>
              <p className="text-[9px] text-[#8a8a8a] tracking-[0.05em] uppercase mt-0.5">Reporting System</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <div className="px-2 py-2 space-y-0.5 border-b border-[#e8e6e1]">
          {([
            { id: 'agent' as View, label: 'Agent', icon: '⬡' },
            { id: 'status' as View, label: 'Report Status', icon: '◫', count: reports.length || undefined },
          ]).map(({ id, label, icon, count }) => {
            const active = view === id;
            return (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[12px] font-medium transition-colors ${
                  active
                    ? 'bg-[#1a1a2e] text-white'
                    : 'text-[#555] hover:bg-[#f0efe9] hover:text-[#1a1a2e]'
                }`}
              >
                <span className={`text-sm ${active ? 'text-cyan-400' : 'text-[#999]'}`}>{icon}</span>
                <span>{label}</span>
                {count && (
                  <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded-full ${
                    active ? 'bg-white/15 text-white/70' : 'bg-[#eee] text-[#888]'
                  }`}>{count}</span>
                )}
              </button>
            );
          })}
        </div>

        {/* TreeFile — reports browser */}
        <div className="flex-1 overflow-y-auto border-b border-[#e8e6e1]">
          <TreeFile />
        </div>

        {/* Data Sources */}
        <div className="h-[180px] overflow-y-auto">
          <DataSources />
        </div>

        {/* Connection */}
        <div className="px-4 py-2 border-t border-[#e8e6e1]">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-[#ccc]'}`} />
            <span className="text-[10px] text-[#8a8a8a]">{connected ? 'Connected' : 'Idle'}</span>
          </div>
        </div>
      </aside>

      {/* ═══ MAIN VIEW ═══ */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {view === 'agent' && <AgentPanel />}
        {view === 'status' && <KanbanBoard />}
      </main>

      <AddSourceDialog />
    </div>
  );
}
