import { useKnownSecretsQuery } from '../queries';
import type { KnownSecret } from '../types';

const UNKNOWN = 'Unknown';

/** One partial-knowledge layer. The backend renders unlocked/unplaced layers as "Unknown"; we
 * style that muted so it reads as a deliberate gap, not missing data. */
function Layer({ label, value }: { label: string; value: string }) {
  const isUnknown = value === UNKNOWN;
  return (
    <div className="text-sm">
      <span className="font-medium">{label}: </span>
      <span className={isUnknown ? 'italic text-muted-foreground' : ''}>{value}</span>
    </div>
  );
}

function SecretCard({ secret }: { secret: KnownSecret }) {
  return (
    <div className="space-y-1 rounded-md border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {secret.level}
        </span>
        <span className="text-xs text-muted-foreground">{secret.author}</span>
      </div>
      <p>{secret.content}</p>
      {secret.second_party && <Layer label="Also implicates" value={secret.second_party} />}
      <Layer label="Category" value={secret.category} />
      <Layer label="Consequences" value={secret.consequences} />
    </div>
  );
}

/** The secret tab on a character's profile: the secrets the viewer knows about this person,
 * with any layer they haven't unlocked shown as "Unknown" (#1334). */
export function SecretsTab({ subjectId }: { subjectId: number }) {
  const { data, isLoading, isError } = useKnownSecretsQuery(subjectId);

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (isError) return <p className="text-destructive">Failed to load secrets.</p>;

  const secrets = data?.results ?? [];
  if (secrets.length === 0) {
    return <p className="text-muted-foreground">You know no secrets about this person.</p>;
  }

  return (
    <div className="space-y-3">
      {secrets.map((secret) => (
        <SecretCard key={secret.id} secret={secret} />
      ))}
    </div>
  );
}
