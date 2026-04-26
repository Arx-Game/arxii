/**
 * StaleStoriesTable — sortable table of stale stories (last advanced > 14 days ago).
 *
 * Default sort: days_stale descending.
 * Story titles are clickable links to /stories/:id.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { formatRelativeTime } from '@/lib/relativeTime';
import type { StaleStoryEntry } from '../types';

type SortKey = 'story_title' | 'last_advanced_at' | 'days_stale';
type SortDir = 'asc' | 'desc';

interface StaleStoriesTableProps {
  entries: StaleStoryEntry[];
}

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-muted-foreground/40">↕</span>;
  return <span className="ml-1">{dir === 'asc' ? '↑' : '↓'}</span>;
}

export function StaleStoriesTable({ entries }: StaleStoriesTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('days_stale');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  if (entries.length === 0) {
    return (
      <p className="py-4 text-muted-foreground" data-testid="stale-stories-empty">
        No stories are stale (last advanced within 14 days).
      </p>
    );
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'story_title' ? 'asc' : 'desc');
    }
  }

  const sorted = [...entries].sort((a, b) => {
    let cmp = 0;
    if (sortKey === 'story_title') {
      cmp = a.story_title.localeCompare(b.story_title);
    } else if (sortKey === 'last_advanced_at') {
      cmp = new Date(a.last_advanced_at).getTime() - new Date(b.last_advanced_at).getTime();
    } else {
      cmp = a.days_stale - b.days_stale;
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <div className="overflow-x-auto" data-testid="stale-stories-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">
              <button
                onClick={() => handleSort('story_title')}
                className="flex items-center hover:text-foreground"
              >
                Story
                <SortIndicator active={sortKey === 'story_title'} dir={sortDir} />
              </button>
            </th>
            <th className="pb-2 pr-4 font-medium">
              <button
                onClick={() => handleSort('last_advanced_at')}
                className="flex items-center hover:text-foreground"
              >
                Last Advanced
                <SortIndicator active={sortKey === 'last_advanced_at'} dir={sortDir} />
              </button>
            </th>
            <th className="pb-2 font-medium">
              <button
                onClick={() => handleSort('days_stale')}
                className="flex items-center hover:text-foreground"
              >
                Days Stale
                <SortIndicator active={sortKey === 'days_stale'} dir={sortDir} />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((entry) => (
            <tr
              key={entry.story_id}
              className="border-b last:border-0 hover:bg-accent/50"
              data-testid="stale-story-row"
            >
              <td className="py-3 pr-4">
                <Link
                  to={`/stories/${entry.story_id}`}
                  className="font-medium text-primary hover:underline"
                >
                  {entry.story_title}
                </Link>
              </td>
              <td className="py-3 pr-4 text-muted-foreground">
                {formatRelativeTime(entry.last_advanced_at)}
              </td>
              <td className="py-3 font-medium tabular-nums text-destructive">{entry.days_stale}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
