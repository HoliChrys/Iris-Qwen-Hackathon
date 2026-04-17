/**
 * TreeFile sidebar — semantic folder structure for published reports.
 * Reports are auto-categorized by the semantic router + LLM tagging.
 * Recurring reports show version history.
 */

import { useState } from 'react';
import { useAtom } from 'jotai';
import { treeAtom, selectedTreeNodeAtom } from '@/stores';
import type { TreeNode } from '@/types';

function TreeItem({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 1);
  const [selected, setSelected] = useAtom(selectedTreeNodeAtom);
  const isSelected = selected === node.id;
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div>
      <div
        onClick={() => {
          if (node.type === 'folder') setExpanded(!expanded);
          setSelected(node.id);
        }}
        className={`flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer text-xs transition ${
          isSelected ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        {/* Expand/collapse */}
        {node.type === 'folder' ? (
          <span className="w-3 text-center text-[10px]">{expanded ? '▾' : '▸'}</span>
        ) : (
          <span className="w-3" />
        )}

        {/* Icon */}
        <span className="text-sm">
          {node.type === 'folder' ? (expanded ? '📂' : '📁') : '📄'}
        </span>

        {/* Name */}
        <span className="flex-1 truncate">{node.name}</span>

        {/* Version count for recurring */}
        {node.version_count && node.version_count > 1 && (
          <span className="text-[9px] text-muted-foreground bg-secondary px-1 rounded">v{node.version_count}</span>
        )}

        {/* Child count for folders */}
        {hasChildren && (
          <span className="text-[9px] text-muted-foreground">{node.children!.length}</span>
        )}
      </div>

      {/* Children */}
      {expanded && hasChildren && (
        <div>
          {node.children!.map((child) => (
            <TreeItem key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function TreeFile() {
  const [tree] = useAtom(treeAtom);

  return (
    <div className="overflow-y-auto py-2">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-3 pb-1 font-medium">
        Reports
      </p>
      {tree.map((node) => (
        <TreeItem key={node.id} node={node} />
      ))}
    </div>
  );
}
