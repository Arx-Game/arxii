/**
 * PerGMQueueTable — sortable table of per-GM queue depth stats.
 *
 * Displays each GM's name, episodes ready, and pending claims.
 * Default sort: episodes_ready descending.
 */

import { useState } from 'react';
import type { PerGMQueueEntry } from '../types';

type SortKey = 'gm_name' | 'episodes_ready' | 'pending_claims';
type SortDir = 'asc' | 'desc';

interface PerGMQueueTableProps {
  entries: PerGMQueueEntry[];
}

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-muted-foreground/40">↕</span>;
  return <span className="ml-1">{dir === 'asc' ? '↑' : '↓'}</span>;
}

export function PerGMQueueTable({ entries }: PerGMQueueTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('episodes_ready');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  if (entries.length === 0) {
    return (
      <p className="py-4 text-muted-foreground" data-testid="per-gm-empty">
        No GM workload data right now.
      </p>
    );
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'gm_name' ? 'asc' : 'desc');
    }
  }

  const sorted = [...entries].sort((a, b) => {
    let cmp = 0;
    if (sortKey === 'gm_name') {
      cmp = a.gm_name.localeCompare(b.gm_name);
    } else {
      cmp = a[sortKey] - b[sortKey];
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <div className="overflow-x-auto" data-testid="per-gm-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">
              <button
                onClick={() => handleSort('gm_name')}
                className="flex items-center hover:text-foreground"
              >
                GM
                <SortIndicator active={sortKey === 'gm_name'} dir={sortDir} />
              </button>
            </th>
            <th className="pb-2 pr-4 font-medium">
              <button
                onClick={() => handleSort('episodes_ready')}
                className="flex items-center hover:text-foreground"
              >
                Episodes Ready
                <SortIndicator active={sortKey === 'episodes_ready'} dir={sortDir} />
              </button>
            </th>
            <th className="pb-2 font-medium">
              <button
                onClick={() => handleSort('pending_claims')}
                className="flex items-center hover:text-foreground"
              >
                Pending Claims
                <SortIndicator active={sortKey === 'pending_claims'} dir={sortDir} />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((entry) => (
            <tr
              key={entry.gm_profile_id}
              className="border-b last:border-0 hover:bg-accent/50"
              data-testid="per-gm-row"
            >
              <td className="py-3 pr-4 font-medium">{entry.gm_name}</td>
              <td className="py-3 pr-4 tabular-nums">{entry.episodes_ready}</td>
              <td className="py-3 tabular-nums">{entry.pending_claims}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
