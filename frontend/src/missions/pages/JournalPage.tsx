/**
 * JournalPage — the full mission ledger (#885).
 *
 * Compass-and-ledger only, by design: active stories (where the current
 * beat can happen, the framing prose, your recorded deeds) and history
 * (how concluded runs ended). Live options never render here — acting
 * happens in the world, via the story tray / beat card in the game view.
 * Exact figures (deed outcomes) live here per the ledger register; the
 * IC prose stays qualitative.
 */
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useState } from 'react';

import { OpportunitiesTab } from '../components/OpportunitiesTab';
import { PendingInvitesSection } from '../components/PendingInvitesSection';
import { useJournal, usePendingInvites, useTellTale } from '../queries';
import type { JournalEntry } from '../types';

export function JournalPage() {
  const { data, isLoading, isError } = useJournal();
  const entries = data?.results ?? [];
  const active = entries.filter((entry) => entry.status === 'active');
  const past = entries.filter((entry) => entry.status !== 'active');
  // Dedicated endpoint (2026-07 audit): reading entries[0].pending_invites
  // meant a character with an empty journal (a brand-new PC invited to their
  // first mission) never saw the invite.
  const { data: pendingInvites = [] } = usePendingInvites();

  return (
    <div className="container mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-4 text-2xl font-semibold">Journal</h1>
      {isError ? (
        <p className="text-sm text-destructive">Couldn't load your journal.</p>
      ) : isLoading ? (
        <p className="text-sm text-muted-foreground">…</p>
      ) : (
        <div className="space-y-6">
          <OpportunitiesTab />
          <PendingInvitesSection invites={pendingInvites} />
          <section className="space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
              Active stories
            </h2>
            {active.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing in motion.</p>
            ) : (
              active.map((entry) => <JournalEntryCard key={entry.instance_id} entry={entry} />)
            )}
          </section>
          <section className="space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
              Concluded
            </h2>
            {past.length === 0 ? (
              <p className="text-sm text-muted-foreground">No stories concluded yet.</p>
            ) : (
              past.map((entry) => <JournalEntryCard key={entry.instance_id} entry={entry} />)
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function JournalEntryCard({ entry }: { entry: JournalEntry }) {
  return (
    <Card data-testid={`journal-entry-${entry.instance_id}`}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{entry.template_name}</CardTitle>
          <Badge variant={entry.status === 'active' ? 'default' : 'secondary'}>
            {entry.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {entry.summary ? (
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{entry.summary}</p>
        ) : null}
        {entry.status === 'active' ? (
          <>
            {entry.current_node_flavor ? (
              <p className="whitespace-pre-wrap text-sm">{entry.current_node_flavor}</p>
            ) : null}
            <Compass entry={entry} />
          </>
        ) : null}
        {entry.epilogue ? (
          <p className="whitespace-pre-wrap text-sm italic">{entry.epilogue}</p>
        ) : null}
        {entry.deeds.length > 0 ? (
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Your deeds
            </div>
            <ul className="mt-1 space-y-0.5 text-sm">
              {entry.deeds.map((deed, idx) => (
                <li key={idx} className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">{deed.node_key}</span>
                  {deed.outcome_name ? <Badge variant="outline">{deed.outcome_name}</Badge> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <TaleSection entry={entry} />
      </CardContent>
    </Card>
  );
}

function TaleSection({ entry }: { entry: JournalEntry }) {
  const tellTale = useTellTale();
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);

  if (entry.tale && !editing) {
    return (
      <div data-testid={`tale-${entry.instance_id}`}>
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Your tale
        </div>
        <p className="mt-1 whitespace-pre-wrap text-sm italic">{entry.tale}</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-1 h-6 text-xs"
          onClick={() => {
            setText(entry.tale ?? '');
            setEditing(true);
          }}
        >
          Edit
        </Button>
      </div>
    );
  }

  if (!entry.can_tell_tale && !editing) {
    return null;
  }

  return (
    <div data-testid={`tale-editor-${entry.instance_id}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {entry.tale ? 'Edit your tale' : 'Tell the tale'}
      </div>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="How did it really happen?"
        className="mt-1 min-h-24 text-sm"
        maxLength={5000}
      />
      <p className="mt-1 text-xs text-muted-foreground">
        Your narration is canon by default. Impossible elaborations are braggadocio — handled
        in-world, never moderated.
      </p>
      <Button
        size="sm"
        className="mt-2"
        disabled={!text.trim() || tellTale.isPending}
        onClick={() => {
          tellTale.mutate(
            { instanceId: entry.instance_id, text: text.trim() },
            {
              onSuccess: () => {
                setEditing(false);
                setText('');
              },
            }
          );
        }}
      >
        {tellTale.isPending ? 'Saving…' : 'Save tale'}
      </Button>
      {editing ? (
        <Button variant="ghost" size="sm" className="mt-2 h-8" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      ) : null}
    </div>
  );
}

function Compass({ entry }: { entry: JournalEntry }) {
  if (entry.compass_anywhere) {
    return <p className="text-xs text-muted-foreground">This story follows you.</p>;
  }
  if (entry.compass_rooms.length === 0) {
    return null;
  }
  return (
    <p className="text-xs text-muted-foreground" data-testid="journal-compass">
      Where: {entry.compass_rooms.join(' · ')}
    </p>
  );
}
