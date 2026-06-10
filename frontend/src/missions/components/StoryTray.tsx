/**
 * StoryTray — the persistent "your active stories" panel (#885).
 *
 * Lives as the Stories tab of the game sidebar. One row per active
 * mission: name, a live dot when options are actionable in the current
 * room, and the compass line (where this beat can happen). Expanding a
 * row opens its BeatCard. The tray never hosts non-live options — the
 * journal page carries the full ledger/history.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

import { BeatCard } from './BeatCard';
import { useBeat, useJournal } from '../queries';
import type { JournalEntry } from '../types';

interface StoryTrayProps {
  /** Stable identifier of the player's current room (refetch key). */
  roomKey: string;
}

export function StoryTray({ roomKey }: StoryTrayProps) {
  const { data, isLoading } = useJournal();
  const [openId, setOpenId] = useState<number | null>(null);
  const active = (data?.results ?? []).filter((entry) => entry.status === 'active');

  if (isLoading) {
    return <div className="p-3 text-sm text-muted-foreground">…</div>;
  }
  if (active.length === 0) {
    return (
      <div className="space-y-2 p-3 text-sm text-muted-foreground" data-testid="story-tray-empty">
        <p>No stories pull at you right now.</p>
        <Link to="/journal" className="text-xs underline">
          Open your journal
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2" data-testid="story-tray">
      {active.map((entry) => (
        <StoryRow
          key={entry.instance_id}
          entry={entry}
          roomKey={roomKey}
          open={openId === entry.instance_id}
          onToggle={() => setOpenId(openId === entry.instance_id ? null : entry.instance_id)}
        />
      ))}
      <div className="px-1">
        <Link to="/journal" className="text-xs text-muted-foreground underline">
          Full journal →
        </Link>
      </div>
    </div>
  );
}

function StoryRow({
  entry,
  roomKey,
  open,
  onToggle,
}: {
  entry: JournalEntry;
  roomKey: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { data: beat } = useBeat(entry.instance_id, roomKey);
  const liveHere = (beat?.options.length ?? 0) > 0;

  return (
    <div className="rounded border" data-testid={`story-row-${entry.instance_id}`}>
      <Button
        variant="ghost"
        className="h-auto w-full justify-between whitespace-normal px-2 py-1.5 text-left"
        onClick={onToggle}
      >
        <span className="text-sm font-medium">{entry.template_name}</span>
        {liveHere ? (
          <span
            className="ml-2 h-2 w-2 shrink-0 rounded-full bg-primary"
            data-testid="story-live-dot"
            title="You can act on this here"
          />
        ) : null}
      </Button>
      {!open ? <CompassLine entry={entry} /> : null}
      {open ? <BeatCard instanceId={entry.instance_id} roomKey={roomKey} /> : null}
    </div>
  );
}

function CompassLine({ entry }: { entry: JournalEntry }) {
  if (entry.compass_anywhere) {
    return <p className="px-2 pb-1.5 text-xs text-muted-foreground">This follows you.</p>;
  }
  if (entry.compass_rooms.length === 0) {
    return null;
  }
  return (
    <p className="px-2 pb-1.5 text-xs text-muted-foreground" data-testid="story-compass">
      {entry.compass_rooms.join(' · ')}
    </p>
  );
}
