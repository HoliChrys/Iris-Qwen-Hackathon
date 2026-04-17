/**
 * Data Sources panel — dynamic topics bound to webhooks.
 * Can add new sources at runtime (serverless Ray spawning).
 */

import { useState } from 'react';
import { useAtom } from 'jotai';
import { dataSourcesAtom, addSourceDialogAtom } from '@/stores';
import type { DataSource } from '@/types';

const TYPE_ICONS: Record<string, string> = {
  kafka_topic: '📡',
  clickhouse_table: '🗄️',
  webhook: '🔗',
  api: '🌐',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-500',
  paused: 'bg-amber-500',
  error: 'bg-red-500',
};

function SourceItem({ source }: { source: DataSource }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition">
      <span>{TYPE_ICONS[source.type] || '📁'}</span>
      <div className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[source.status]}`} />
      <span className="flex-1 truncate">{source.name}</span>
      <span className="text-[9px] opacity-60">{source.events_count}</span>
    </div>
  );
}

export function DataSources() {
  const [sources] = useAtom(dataSourcesAtom);
  const [, setAddOpen] = useAtom(addSourceDialogAtom);

  return (
    <div className="py-2">
      <div className="flex items-center justify-between px-3 pb-1">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Data Sources</p>
        <button
          onClick={() => setAddOpen(true)}
          className="text-[10px] text-muted-foreground hover:text-foreground"
        >
          + Add
        </button>
      </div>
      {sources.map((s) => (
        <SourceItem key={s.id} source={s} />
      ))}
    </div>
  );
}

export function AddSourceDialog() {
  const [open, setOpen] = useAtom(addSourceDialogAtom);
  const [sources, setSources] = useAtom(dataSourcesAtom);
  const [name, setName] = useState('');
  const [type, setType] = useState<DataSource['type']>('webhook');
  const [endpoint, setEndpoint] = useState('');

  if (!open) return null;

  const handleAdd = () => {
    if (!name.trim() || !endpoint.trim()) return;
    setSources((prev) => [...prev, {
      id: `ds-${crypto.randomUUID().slice(0, 8)}`,
      name: name.trim(),
      type,
      endpoint: endpoint.trim(),
      status: 'active',
      events_count: 0,
      bound_agents: [],
    }]);
    setName('');
    setEndpoint('');
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card border border-border rounded-xl p-5 w-[400px] shadow-2xl">
        <h3 className="text-sm font-semibold mb-4">Add Data Source</h3>

        <div className="space-y-3">
          <div>
            <label className="text-[11px] text-muted-foreground block mb-1">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. live-transactions"
              className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground block mb-1">Type</label>
            <select value={type} onChange={(e) => setType(e.target.value as DataSource['type'])}
              className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm">
              <option value="webhook">Webhook</option>
              <option value="kafka_topic">Kafka Topic</option>
              <option value="clickhouse_table">ClickHouse Table</option>
              <option value="api">API Endpoint</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground block mb-1">Endpoint / URL</label>
            <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://... or topic name"
              className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>

        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={() => setOpen(false)} className="btn btn-ghost px-4 py-2">Cancel</button>
          <button onClick={handleAdd} className="btn btn-primary px-4 py-2">Add Source</button>
        </div>
      </div>
    </div>
  );
}
