/**
 * Search hook — queries the SB5 search backend (Neo4j + ClickHouse + Graphiti).
 */

import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';

const API_BASE = '/api';

export interface SearchResult {
  source: string;
  report_id?: string;
  request_id?: string;
  entity_id?: string;
  report_title?: string;
  query_text?: string;
  department?: string;
  report_type?: string;
  status?: string;
  state?: string;
  chart_count?: number;
  compliance_score?: number;
  created_at?: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  sources_queried: string[];
}

export function useSearch() {
  const [results, setResults] = useState<SearchResponse | null>(null);

  const searchMutation = useMutation({
    mutationFn: async (query: string): Promise<SearchResponse> => {
      const res = await fetch(`${API_BASE}/sb5/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, max_results: 20 }),
      });
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);
      return res.json();
    },
    onSuccess: (data) => setResults(data),
  });

  const search = useCallback((query: string) => {
    if (query.trim()) searchMutation.mutate(query.trim());
  }, [searchMutation]);

  return {
    search,
    results,
    isSearching: searchMutation.isPending,
    error: searchMutation.error,
  };
}
