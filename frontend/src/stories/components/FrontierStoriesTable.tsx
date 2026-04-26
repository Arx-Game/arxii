/**
 * FrontierStoriesTable — table of stories currently at the authoring frontier.
 *
 * Story titles are clickable links to /stories/:id.
 * Scope shown as a badge.
 */

import { Link } from 'react-router-dom';
import { ScopeBadge } from './ScopeBadge';
import type { FrontierStoryEntry } from '../types';

interface FrontierStoriesTableProps {
  entries: FrontierStoryEntry[];
}

export function FrontierStoriesTable({ entries }: FrontierStoriesTableProps) {
  if (entries.length === 0) {
    return (
      <p className="py-4 text-muted-foreground" data-testid="frontier-stories-empty">
        No stories at the authoring frontier.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="frontier-stories-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Story</th>
            <th className="pb-2 font-medium">Scope</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr
              key={entry.story_id}
              className="border-b last:border-0 hover:bg-accent/50"
              data-testid="frontier-story-row"
            >
              <td className="py-3 pr-4">
                <Link
                  to={`/stories/${entry.story_id}`}
                  className="font-medium text-primary hover:underline"
                >
                  {entry.story_title}
                </Link>
              </td>
              <td className="py-3">
                <ScopeBadge scope={entry.scope} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
