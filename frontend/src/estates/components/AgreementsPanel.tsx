import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  useClaimsQuery,
  useSettlementsQuery,
  useWillMutations,
  useWillQuery,
} from '../estatesQueries';
import { BequestEditor } from './BequestEditor';
import { ExecutorEditor } from './ExecutorEditor';

interface AgreementsPanelProps {
  /** CharacterSheet pk (== character ObjectDB pk) of the viewed own character. */
  characterSheetId: number;
}

/**
 * The agreements hub (#1985): binding declarations that fire later.
 * V1 content is the will; vows, oaths, treaties, and pacts join as they ship.
 */
export function AgreementsPanel({ characterSheetId }: AgreementsPanelProps) {
  const { data: will, isLoading } = useWillQuery(characterSheetId);
  const { data: settlements } = useSettlementsQuery();
  const { data: claims } = useClaimsQuery();
  const mutations = useWillMutations(characterSheetId);
  const [testament, setTestament] = useState<string | null>(null);

  if (isLoading) return <p className="p-4">Loading agreements…</p>;

  const frozen = will?.is_frozen ?? false;
  const testamentValue = testament ?? will?.testament_text ?? '';

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h3 className="text-xl font-semibold">Last Will &amp; Testament</h3>
        {frozen && (
          <p className="rounded border border-amber-500 bg-amber-500/10 p-2 text-sm">
            This will is sealed — the estate is being settled.
          </p>
        )}
        {!will && (
          <p className="text-sm text-muted-foreground">
            No will written. Declare where your belongings go — otherwise your estate falls to your
            house, then next of kin, then the crown of the region.
          </p>
        )}
        <Textarea
          value={testamentValue}
          onChange={(e) => setTestament(e.target.value)}
          placeholder="The testament read aloud at your will-reading…"
          disabled={frozen}
          rows={4}
        />
        <Button
          size="sm"
          disabled={frozen || mutations.createWill.isPending || mutations.updateTestament.isPending}
          onClick={() => {
            if (will) {
              mutations.updateTestament.mutate({ willId: will.id, testamentText: testamentValue });
            } else {
              mutations.createWill.mutate(testamentValue);
            }
          }}
        >
          {will ? 'Update testament' : 'Write will'}
        </Button>
      </section>

      {will && (
        <>
          <BequestEditor will={will} frozen={frozen} mutations={mutations} />
          <ExecutorEditor will={will} frozen={frozen} mutations={mutations} />
        </>
      )}

      {settlements && settlements.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xl font-semibold">Estates Awaiting You</h3>
          <p className="text-sm text-muted-foreground">
            You are named executor. Hold a will-reading in the game, or a funeral's rites will carry
            it; unattended estates settle on their own at the deadline.
          </p>
          <ul className="space-y-1">
            {settlements.map((s) => (
              <li key={s.id} className="rounded border p-2 text-sm">
                <span className="font-medium">{s.deceased_name}</span> — settles by{' '}
                {new Date(s.deadline).toLocaleDateString()}
              </li>
            ))}
          </ul>
        </section>
      )}

      {claims && claims.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xl font-semibold">Inherited Claims</h3>
          <p className="text-sm text-muted-foreground">
            Possessions stolen from the departed, never recovered. The record of what is owed passed
            to you.
          </p>
          <ul className="space-y-1">
            {claims.map((c) => (
              <li key={c.id} className="rounded border p-2 text-sm">
                {c.item_name}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
