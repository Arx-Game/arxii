/**
 * JournalTab — the sidebar "Journal" tab content (#2160).
 *
 * A compose button (opens `JournalComposerDialog`) plus the player's 5
 * most recent entries (title + date, linking through to `/journals` for
 * the full page). Responses-to-me isn't surfaced here — the `mine/` feed
 * doesn't return a per-entry "who responded to this" count cheaply (only
 * `response_count`, which includes the author's own follow-ups), so a real
 * "responses to me" count would need a new backend shape; out of scope for
 * this task per the brief (no backend changes).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useMyJournalEntries } from '../queries';
import { JournalComposerDialog } from './JournalComposerDialog';

export function JournalTab() {
  const [composerOpen, setComposerOpen] = useState(false);
  const { data, isLoading } = useMyJournalEntries();
  const recent = (data?.results ?? []).slice(0, 5);

  return (
    <div className="space-y-3 p-3">
      <Button
        size="sm"
        className="w-full gap-1.5"
        onClick={() => setComposerOpen(true)}
        data-testid="journal-tab-compose"
      >
        <PenLine className="h-3.5 w-3.5" />
        Write an entry
      </Button>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : recent.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="journal-tab-empty">
          You haven&apos;t written anything yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {recent.map((entry) => (
            <li key={entry.id}>
              <Link
                to="/journals"
                className="block rounded border px-2 py-1.5 text-sm hover:bg-accent"
              >
                <span className="block truncate font-medium">{entry.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {new Date(entry.created_at).toLocaleDateString()}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Link to="/journals" className="block text-xs text-muted-foreground underline">
        Full journal →
      </Link>

      <JournalComposerDialog open={composerOpen} onClose={() => setComposerOpen(false)} />
    </div>
  );
}
