/**
 * ForeignRelationshipTimeline (#2159) — `RelationshipPanel`'s foreign-sheet
 * arm. Reads Task 2's `?about_character=` timeline arm: every non-PRIVATE
 * writeup about the viewed character from any author, plus PRIVATE writeups
 * where the caller's account is the author's or the subject's (see
 * `RelationshipUpdateViewSet._timeline_about_character_queryset`).
 *
 * Deliberately shows NO numeric relationship state (points, tiers,
 * affection, absolute value) — `RelationshipTimelineEntry` doesn't even
 * carry those fields; that data is author-private (ADR-0117) and stays on
 * `OwnRelationshipsList`. Only type-tagged (`kind`), categorical writeup
 * content: who wrote it, which track, the title/writeup text, and when.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): entries on hairlines, the kind as
 * a tag, the author and track as the gloss.
 */

import { useRelationshipTimeline } from '../queries';
import { Entries, Entry, Ledger, Tag } from '@/character_sheets/components/sheet/primitives';
import type { RelationshipTimelineEntry } from '../api';

export interface ForeignRelationshipTimelineProps {
  characterSheetId?: number;
}

const KIND_LABELS: Record<RelationshipTimelineEntry['kind'], string> = {
  update: 'Impression',
  development: 'Development',
  capstone: 'Capstone',
};

export function ForeignRelationshipTimeline({
  characterSheetId,
}: ForeignRelationshipTimelineProps) {
  const { data: entries = [], isLoading } = useRelationshipTimeline({
    aboutCharacter: characterSheetId,
  });

  if (isLoading) {
    return <Ledger>Reading what others have written…</Ledger>;
  }

  if (entries.length === 0) {
    return <Ledger>Nobody has written of knowing them yet.</Ledger>;
  }

  return (
    <Entries>
      {entries.map((entry) => (
        <Entry
          key={`${entry.kind}-${entry.id}`}
          name={entry.title}
          tags={<Tag>{KIND_LABELS[entry.kind] ?? entry.kind}</Tag>}
          gloss={`By ${entry.author_name}, on ${entry.track_name}.`}
        >
          <p className="refsheet-entry-gloss">{entry.writeup}</p>
        </Entry>
      ))}
    </Entries>
  );
}
