/**
 * The cast (#3898) — the people and groups the character came from.
 *
 * Built from the sheet payload's origin ties rather than from the relationships API,
 * for two reasons: those ties are already public (the origins block has always shown
 * them to every viewer), and the outbound-relationships list is own-sheet-only, so a
 * cast built from it would be missing for exactly the strangers this page is meant to
 * hold its shape for. The full, living picture is one link away under Ties.
 *
 * A group row names its organization; a person row names the figure and, where one is
 * anchored, the group they belong to.
 */

import { Link } from 'react-router-dom';
import type { CharacterSheetOriginSlot } from '@/character_sheets/api';
import { Heading, Stack } from './primitives';

interface CastRowProps {
  slots: CharacterSheetOriginSlot[];
}

interface CastMember {
  key: string;
  who: string;
  how: string;
  to: string | null;
}

export function CastRow({ slots }: CastRowProps) {
  const members: CastMember[] = [];

  for (const slot of slots) {
    if (slot.kind === 'group' && slot.organization_name) {
      members.push({
        key: `group-${slot.slot_id}`,
        who: slot.organization_name,
        how: slot.connection_kind || slot.slot_name,
        to: slot.organization_id ? `/orgs/${slot.organization_id}` : null,
      });
    } else if (slot.kind === 'person' && slot.figure_name) {
      // `figure_name` is blanked server-side for a non-privileged viewer, so a person
      // the character keeps to themselves never reaches this list at all.
      members.push({
        key: `person-${slot.slot_id}`,
        who: slot.figure_name,
        how: slot.value || slot.organization_name || slot.slot_name,
        to: null,
      });
    }
  }

  if (members.length === 0) return null;

  return (
    <Stack>
      <Heading>The cast</Heading>
      <div className="refsheet-cast">
        {members.map((member) => (
          <div key={member.key} className="refsheet-face">
            <span className="refsheet-face-ring" aria-hidden="true" />
            <span className="refsheet-face-who">
              {member.to ? <Link to={member.to}>{member.who}</Link> : member.who}
            </span>
            {member.how && <span className="refsheet-face-how">{member.how}</span>}
          </div>
        ))}
      </div>
    </Stack>
  );
}
