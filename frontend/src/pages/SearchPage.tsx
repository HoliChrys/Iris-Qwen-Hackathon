/**
 * Search page — search across all reports via Neo4j + ClickHouse + Graphiti.
 *
 * Features:
 * - Natural language search bar
 * - Results grouped by source (Neo4j graph, ClickHouse SQL, Graphiti semantic)
 * - Click to open report in preview
 * - Filter by department, type, status
 */

import { useState, useRef } from 'react';
import { useSearch, type SearchResult } from '@/hooks/useSearch';

const SOURCE_COLORS: Record<string, string> = {
  neo4j: 'bg-purple-500/15 text-purple-400',
  clickhouse: 'bg-blue-500/15 text-blue-400',
  graphiti: 'bg-emerald-500/15 text-emerald-400',
};

const STATUS_COLORS: Record<string, string> = {
  published: 'bg-green-500/15 text-green-500',
  pending_review: 'bg-amber-500/15 text-amber-500',
  rejected: 'bg-red-500/15 text-red-500',
  interpreting: 'bg-blue-500/15 text-blue-400',
};

function ResultCard({ result }: { result: SearchResult }) {
  const title = result.report_title || result.query_text || 'Untitled';
  const id = result.request_id || result.report_id || result.entity_id || '';
  const status = result.status || result.state || 'unknown';

  return (
    <div className="panel p-4 hover:ring-1 hover:ring-ring/30 transition cursor-pointer">
      <div className="flex items-start gap-3">
        <div className="text-2xl mt-0.5">📄</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold truncate">{title}</h4>
          <p className="text-[11px] text-muted-foreground font-mono mt-0.5">{id.slice(0, 12)}...</p>

          <div className="flex flex-wrap gap-1.5 mt-2">
            {result.source && (
              <span className={`badge ${SOURCE_COLORS[result.source] || 'bg-secondary text-muted-foreground'}`}>
                {result.source}
              </span>
            )}
            {status && (
              <span className={`badge ${STATUS_COLORS[status] || 'bg-secondary text-muted-foreground'}`}>
                {status}
              </span>
            )}
            {result.department && (
              <span className="badge bg-secondary text-muted-foreground">{result.department}</span>
            )}
            {result.report_type && (
              <span className="badge bg-secondary text-muted-foreground">{result.report_type}</span>
            )}
            {result.chart_count != null && (
              <span className="badge bg-secondary text-muted-foreground">{result.chart_count} charts</span>
            )}
            {result.compliance_score != null && (
              <span className={`badge ${result.compliance_score >= 0.9 ? 'badge-success' : 'badge-warning'}`}>
                {(result.compliance_score * 100).toFixed(0)}% compliance
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SearchPage() {
  const [query, setQuery] = useState('');
  const { search, results, isSearching } = useSearch();
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSearch = () => {
    if (query.trim()) search(query);
  };

  const quickSearches = [
    'loan portfolio',
    'NPL ratio agence',
    'transactions canal',
    'Strategy Division',
    'branch comparison',
    'Digital Innovation',
    'daily summary',
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {/* Header */}
      <h2 className="text-lg font-semibold mb-1">Search Reports</h2>
      <p className="text-sm text-muted-foreground mb-5">
        Search across Neo4j graph, ClickHouse warehouse, and Graphiti semantic index
      </p>

      {/* Search bar */}
      <div className="flex gap-2 mb-4">
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            placeholder="Search reports... (e.g. 'loan portfolio NPL', 'Strategy Division', 'transactions')"
            className="w-full bg-card border border-input rounded-xl px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {isSearching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
        <button
          onClick={handleSearch}
          disabled={isSearching || !query.trim()}
          className="btn btn-primary px-6 py-3 rounded-xl disabled:opacity-40"
        >
          Search
        </button>
      </div>

      {/* Quick searches */}
      <div className="flex flex-wrap gap-2 mb-6">
        {quickSearches.map((q) => (
          <button
            key={q}
            onClick={() => { setQuery(q); search(q); }}
            className="px-3 py-1.5 rounded-lg text-xs bg-secondary text-muted-foreground hover:text-foreground hover:bg-accent transition"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Results */}
      {results && (
        <>
          {/* Summary */}
          <div className="flex items-center gap-3 mb-4">
            <p className="text-sm">
              <span className="font-semibold">{results.total}</span> results for "
              <span className="font-medium">{results.query}</span>"
            </p>
            <div className="flex gap-1.5">
              {results.sources_queried.map((s) => (
                <span key={s} className={`badge ${SOURCE_COLORS[s] || 'bg-secondary text-muted-foreground'}`}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Result cards */}
          {results.results.length > 0 ? (
            <div className="space-y-2">
              {results.results.map((r, i) => (
                <ResultCard key={r.request_id || r.report_id || r.entity_id || i} result={r} />
              ))}
            </div>
          ) : (
            <div className="panel p-12 text-center">
              <p className="text-3xl mb-2">🔍</p>
              <p className="text-muted-foreground">No reports found for "{results.query}"</p>
              <p className="text-xs text-muted-foreground mt-1">Try different keywords or check available data domains</p>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!results && !isSearching && (
        <div className="panel p-16 text-center">
          <p className="text-5xl mb-3">🔍</p>
          <p className="text-foreground font-medium">Search through all generated reports</p>
          <p className="text-sm text-muted-foreground mt-1">
            Queries are matched against report titles, departments, types, and content
          </p>
          <p className="text-xs text-muted-foreground mt-3">
            Sources: Neo4j (graph relationships) · ClickHouse (SQL tracking) · Graphiti (semantic vectors)
          </p>
        </div>
      )}
    </div>
  );
}
