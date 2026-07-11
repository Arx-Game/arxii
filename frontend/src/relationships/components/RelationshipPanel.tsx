/**
 * RelationshipPanel (#2159) — replaces the old free-text "Notes" subsection
 * on `RelationshipsSection` with the real relationship surface.
 *
 * Branches on `isMyCharacter`, mirroring `CharacterRelationshipViewSet`'s
 * author-private scoping (ADR-0117): the caller's own sheet gets the
 * full-fidelity outbound relationship list (`OwnRelationshipsList` — target
 * names, affection, per-track points/tiers, expandable history, and the
 * development/capstone/redistribute write actions); a foreign sheet gets
 * only the visibility-scoped, type-tagged timeline (`ForeignRelationshipTimeline`
 * — no numeric relationship state at all).
 */

import { ForeignRelationshipTimeline } from './ForeignRelationshipTimeline';
import { OwnRelationshipsList } from './OwnRelationshipsList';

export interface RelationshipPanelProps {
  /** The CharacterSheet pk for the viewed character. */
  characterSheetId?: number;
  /** True only when viewing the CALLER's own character sheet. */
  isMyCharacter?: boolean;
}

export function RelationshipPanel({
  characterSheetId,
  isMyCharacter = false,
}: RelationshipPanelProps) {
  if (isMyCharacter) {
    return <OwnRelationshipsList characterSheetId={characterSheetId} />;
  }
  return <ForeignRelationshipTimeline characterSheetId={characterSheetId} />;
}
