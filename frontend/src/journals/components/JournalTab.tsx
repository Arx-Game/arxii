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
 *
 * VoteButton gating (#3302): `entries/mine/` is filtered server-side to the
 * requesting character's own entries only (`views.py`'s `mine` action), so
 * every row here is always the viewer's own; the same own-entry gate used
 * on `JournalsPage` therefore always evaluates to hidden. Wired anyway (not
 * dead: it's the correctness gate, not a feature) so this list renders
 * VoteButton the moment it ever surfaces someone else's entry.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { VoteButton } from '@/components/VoteButton';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useMyJournalEntries } from '../queries';
import { JournalComposerDialog } from './JournalComposerDialog';

export function JournalTab() {
  const [composerOpen, setComposerOpen] = useState(false);
  const { data, isLoading } = useMyJournalEntries();
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const recent = (data?.results ?? []).slice(0, 5);

  const renderRecent = () => {
    if (isLoading) {
      return <p className="text-sm text-muted-foreground">Loading…</p>;
    }
    if (recent.length === 0) {
      return (
        <p className="text-sm text-muted-foreground" data-testid="journal-tab-empty">
          You haven&apos;t written anything yet.
        </p>
      );
    }
    return (
      <ul className="space-y-2">
        {recent.map((entry) => {
          const isOwnEntry = myRosterEntries.some((e) => e.character_id === entry.author);
          const canVote = entry.is_public && !isOwnEntry;
          return (
            <li key={entry.id} className="flex items-center gap-1">
              <Link
                to="/journals"
                className="block min-w-0 flex-1 rounded border px-2 py-1.5 text-sm hover:bg-accent"
              >
                <span className="block truncate font-medium">{entry.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {new Date(entry.created_at).toLocaleDateString()}
                </span>
              </Link>
              {canVote ? <VoteButton targetType="journal" targetId={entry.id} /> : null}
            </li>
          );
        })}
      </ul>
    );
  };

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

      {renderRecent()}

      <Link to="/journals" className="block text-xs text-muted-foreground underline">
        Full journal →
      </Link>

      <JournalComposerDialog open={composerOpen} onClose={() => setComposerOpen(false)} />
    </div>
  );
}
