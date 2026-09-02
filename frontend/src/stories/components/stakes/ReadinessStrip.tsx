/**
 * ReadinessStrip (#3561) - the beat's readiness verdict + open-activation
 * lock banner, factored out of `BeatFormDialog`'s inline copy so
 * `StakesPanel`'s header can show the same block without duplicating it.
 *
 * Self-fetches `useBeatReadiness`/`useOpenBeatActivation` (#3562) by beat id
 * - both hooks share a query key with any other mount reading the same
 * beat, so this never causes a second network round trip.
 */

import { useBeatReadiness, useOpenBeatActivation } from '../../queries';
import { riskLabel } from './constants';

interface ReadinessStripProps {
  beatId: number;
}

export function ReadinessStrip({ beatId }: ReadinessStripProps) {
  const readinessQuery = useBeatReadiness(beatId, true);
  const activationQuery = useOpenBeatActivation(beatId, true);
  const readiness = readinessQuery.data;
  const openActivation = activationQuery.data?.[0] ?? null;

  return (
    <div className="space-y-1 rounded-md border p-3 text-sm" data-testid="stakes-readiness-strip">
      {readiness && (
        <>
          <p className="font-medium" data-testid="stakes-readiness-verdict">
            {readiness.is_ready ? 'Ready' : 'Not ready'}
          </p>
          {readiness.problems.length > 0 && (
            <ul
              className="list-disc space-y-0.5 pl-4 text-xs text-destructive"
              data-testid="stakes-readiness-problems"
            >
              {readiness.problems.map((problem, i) => (
                <li key={i}>{problem}</li>
              ))}
            </ul>
          )}
          {readiness.advisories.length > 0 && (
            <ul
              className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground"
              data-testid="stakes-readiness-advisories"
            >
              {readiness.advisories.map((advisory, i) => (
                <li key={i}>{advisory}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">
            Declared risk: {riskLabel(readiness.declared_risk)} · Effective risk:{' '}
            {riskLabel(readiness.effective_risk)}
          </p>
        </>
      )}
      {openActivation && (
        <p
          className="rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-xs"
          data-testid="stakes-lock-banner"
        >
          Locked while the scene runs
        </p>
      )}
    </div>
  );
}
