/**
 * WantedBoard (#1826/#2378) — the area's public justice picture, rendered where a
 * civic hub stands (notice board / town crier).
 *
 * Three public blocks: the wanted list (tier + presented name + alleged crimes,
 * never raw numbers), the held-for-trial list (being held is a public record —
 * and the discovery seam for the help-the-accused loop: anyone can submit
 * exculpatory evidence, help only, never hurt), and — for viewers holding pardon
 * power here — the lord's-grant control per wanted row.
 */

import { useState } from 'react';
import { Gavel, Loader2 } from 'lucide-react';

import { usePardonMutation, useSubmitEvidenceMutation, useWantedList } from '../queries';
import { Button } from '@/components/ui/button';

interface Props {
  areaId: number;
  /** The viewer's active RosterEntry pk; null when unknown (board stays read-only). */
  viewerEntryId: number | null;
}

const TIER_STYLES: Record<string, string> = {
  heat_is_on: 'bg-red-500/15 text-red-600 dark:text-red-400',
  extreme_heat: 'bg-red-600/25 text-red-700 dark:text-red-300',
};

export function WantedBoard({ areaId, viewerEntryId }: Props) {
  const { data, isLoading } = useWantedList(areaId, viewerEntryId);
  const pardon = usePardonMutation(viewerEntryId);
  const evidence = useSubmitEvidenceMutation(viewerEntryId);
  const [evidenceFor, setEvidenceFor] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="flex justify-center py-2">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!data || (data.wanted.length === 0 && data.held.length === 0)) {
    return null;
  }

  return (
    <div className="border-b px-3 py-2" data-testid="wanted-board">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Gavel className="h-3 w-3" />
        Wanted here
      </div>
      {data.wanted.length > 0 && (
        <ul className="space-y-1">
          {data.wanted.map((row) => (
            <li key={`${row.persona_id}-${row.society_name}`} className="text-xs">
              <span
                className={`mr-1 rounded-full px-1.5 py-0.5 font-medium ${TIER_STYLES[row.tier] ?? 'bg-muted text-muted-foreground'}`}
              >
                {row.tier_label}
              </span>
              <span className="font-semibold">{row.persona_name}</span>
              <span className="text-muted-foreground"> — sought by {row.society_name}</span>
              {row.crimes.length > 0 && (
                <span className="text-muted-foreground"> for {row.crimes.join(', ')}</span>
              )}
              {data.viewer_can_pardon && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-1 h-5 px-1.5 text-xs"
                  disabled={pardon.isPending}
                  onClick={() => pardon.mutate({ areaId, targetPersonaId: row.persona_id })}
                  title="A lord's grant: clear this persona's standing with the hunters here. A public act."
                >
                  Grant pardon
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.held.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            Held for trial
          </div>
          <ul className="space-y-1">
            {data.held.map((row) => (
              <li key={row.case_id} className="text-xs">
                <span className="font-semibold">{row.persona_name}</span>
                {viewerEntryId !== null && evidenceFor !== row.case_id && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-1 h-5 px-1.5 text-xs"
                    onClick={() => setEvidenceFor(row.case_id)}
                  >
                    Help them
                  </Button>
                )}
                {evidenceFor === row.case_id && (
                  <span className="ml-1 inline-flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-5 px-1.5 text-xs"
                      disabled={evidence.isPending}
                      onClick={() => {
                        evidence.mutate({ caseId: row.case_id, manufactured: false });
                        setEvidenceFor(null);
                      }}
                      title="Present genuine exculpatory evidence to the magistrates."
                    >
                      Submit evidence
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-5 px-1.5 text-xs"
                      disabled={evidence.isPending}
                      onClick={() => {
                        evidence.mutate({ caseId: row.case_id, manufactured: true });
                        setEvidenceFor(null);
                      }}
                      title="Manufacture evidence. Convincing if it holds; a crime of its own if exposed."
                    >
                      Manufacture it
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(pardon.isError || evidence.isError) && (
        <p className="mt-1 text-xs text-destructive">
          {[pardon.error, evidence.error]
            .filter((e): e is Error => e instanceof Error)
            .map((e) => e.message)
            .join(' ')}
        </p>
      )}
      {pardon.isSuccess && <p className="mt-1 text-xs text-muted-foreground">The grant is made.</p>}
      {evidence.isSuccess && (
        <p className="mt-1 text-xs text-muted-foreground">
          Your submission reaches the magistrates.
        </p>
      )}
    </div>
  );
}
