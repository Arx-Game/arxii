/**
 * SecretsTab — the secrets the active viewing character knows about this person.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): an entry per secret, its level as
 * the tag and its teller pulled right, with the partial-knowledge layers as a glance
 * list underneath. A layer the viewer has not unlocked reads "Unknown" in the muted
 * voice, which is the point — the gap is deliberate, not missing data.
 */

import { useKnownSecretsQuery } from '../queries';
import type { KnownSecret } from '../types';
import {
  Entries,
  Entry,
  Glance,
  Ledger,
  Tag,
} from '@/character_sheets/components/sheet/primitives';
import type { GlanceRow } from '@/character_sheets/components/sheet/primitives';

import { GrievancePrompt } from './GrievancePrompt';

const UNKNOWN = 'Unknown';

/** A layer's value, italicised when it is a gap the viewer has not closed. */
function layerValue(value: string) {
  return value === UNKNOWN ? <em className="refsheet-soft">{value}</em> : value;
}

function SecretEntry({ secret, viewerId }: { secret: KnownSecret; viewerId: number }) {
  const rows: GlanceRow[] = [
    { label: 'Category', value: layerValue(secret.category) },
    { label: 'Consequences', value: layerValue(secret.consequences) },
    {
      label: 'The truth behind',
      value: secret.anchored_to.map((anchor) => anchor.label).join(', '),
    },
  ];
  return (
    <Entry
      name={secret.content}
      aside={<span className="refsheet-note">{secret.author}</span>}
      tags={<Tag>{secret.level}</Tag>}
    >
      <Glance rows={rows} />
      {secret.can_grieve && <GrievancePrompt secretId={secret.id} viewerId={viewerId} />}
    </Entry>
  );
}

/** The secret tab on a character's profile: the secrets the **active viewing character** knows
 * about this person, with any layer they haven't unlocked shown as "Unknown" (#1334). IC
 * knowledge is per active character — `viewerId` is the viewer's active RosterEntry, or null. */
export function SecretsTab({
  subjectId,
  viewerId,
}: {
  subjectId: number;
  viewerId: number | null;
}) {
  const { data, isLoading, isError } = useKnownSecretsQuery(subjectId, viewerId);

  if (viewerId === null) {
    return <Ledger>Choose a character to see the secrets they keep about this one.</Ledger>;
  }
  if (isLoading) return <Ledger>Reading what you know…</Ledger>;
  if (isError) {
    return (
      <p className="refsheet-ledger" style={{ color: 'hsl(var(--destructive))' }}>
        Those secrets could not be read.
      </p>
    );
  }

  const secrets = data?.results ?? [];
  if (secrets.length === 0) {
    return <Ledger>You know nothing of theirs.</Ledger>;
  }

  return (
    <Entries>
      {secrets.map((secret) => (
        <SecretEntry key={secret.id} secret={secret} viewerId={viewerId} />
      ))}
    </Entries>
  );
}
