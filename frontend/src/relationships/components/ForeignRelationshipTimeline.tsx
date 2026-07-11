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
 */

import { Badge } from '@/components/ui/badge';
import { useRelationshipTimeline } from '../queries';
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
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No visible relationship history yet.</p>;
  }

  return (
    <ul className="space-y-4">
      {entries.map((entry) => (
        <li key={`${entry.kind}-${entry.id}`} className="border-b pb-3">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{KIND_LABELS[entry.kind] ?? entry.kind}</Badge>
            <span className="font-medium">{entry.title}</span>
          </div>
          <p className="text-sm text-muted-foreground">
            By {entry.author_name} &middot; {entry.track_name}
          </p>
          <p className="mt-1">{entry.writeup}</p>
        </li>
      ))}
    </ul>
  );
}
