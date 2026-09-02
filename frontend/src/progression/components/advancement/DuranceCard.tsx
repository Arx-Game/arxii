/**
 * DuranceCard (#3045) — the Ritual of the Durance readiness hub + convene/join flow.
 *
 * Status: GET /api/progression/durance/status/ (DuranceStatusView) — mirrors
 * telnet `durance status` exactly (same selectors/services), no wider read
 * (#3045 spec's "Verified leak analysis": no wider serializer than telnet's
 * own output).
 *
 * Intent declare/clear reuses the EXISTING PathIntent seam (#954 —
 * `usePathIntent`/`useDeclarePathIntent`/`useClearPathIntent`,
 * `@/magic/queries`) against THIS card's own `eligible_paths` list — NOT
 * `useNextPathOptions`, which is a materially different, unfiltered-by-stage
 * query (see `world/progression/selectors.py`'s `eligible_advanced_paths_for`
 * vs `next_path_options`).
 *
 * Convene: POST /api/progression/durance/convene/ (DuranceConveneView) — a
 * plain service call over `convene_durance_at_site`, mirroring telnet
 * `durance convene`.
 *
 * Join: POST /api/magic/rituals/sessions/{id}/accept/ — auto-fires for a
 * site-convened session (#3045 backend fix to `RitualSessionViewSet.accept`,
 * matching telnet's `ritual join` auto-fire — there is no live initiator for
 * the player to separately `fire`).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useClearPathIntent, useDeclarePathIntent, usePathIntent } from '@/magic/queries';
import {
  useConveneDuranceMutation,
  useDuranceStatusQuery,
  useJoinDuranceSessionMutation,
} from '@/progression/queries';

interface DuranceCardProps {
  characterId: number;
}

export function DuranceCard({ characterId }: DuranceCardProps) {
  const { data: status, isLoading, error } = useDuranceStatusQuery();
  const { data: intentData } = usePathIntent(characterId);
  const declareIntent = useDeclarePathIntent();
  const clearIntent = useClearPathIntent();
  const convene = useConveneDuranceMutation();
  const join = useJoinDuranceSessionMutation();

  const [openSessionId, setOpenSessionId] = useState<number | null>(null);
  const [testament, setTestament] = useState('');

  function handleConvene() {
    convene.mutate(undefined, {
      onSuccess: (result) => {
        setOpenSessionId(result.session_id);
        toast.success('The Durance is convened — speak your testament to join.');
      },
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : 'Could not convene the Durance.'),
    });
  }

  function handleJoin() {
    if (openSessionId === null || testament.trim() === '') return;
    join.mutate(
      { sessionId: openSessionId, participantKwargs: { testament: testament.trim() } },
      {
        onSuccess: (result) => {
          toast.success(
            result.fired
              ? 'The rite is complete — your level has advanced.'
              : 'You have joined the Durance session.'
          );
          setOpenSessionId(null);
          setTestament('');
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not join the Durance.'),
      }
    );
  }

  const declaredPathId = intentData?.intent?.intended_path.id ?? null;

  // Takes the gate rather than reading `status`: the call site is inside a
  // `{status && ...}` guard, and TypeScript does not flow that narrowing into a
  // closure declared above it.
  const renderUnlockStatus = (gate: NonNullable<NonNullable<typeof status>['unlock_gate']>) => {
    if (gate.purchased) {
      return 'purchased';
    }
    if (gate.xp_cost === 0) {
      return (
        <Badge variant="outline" data-testid="durance-cost-unset">
          Cost unset (staff)
        </Badge>
      );
    }
    return `not purchased (cost ${gate.xp_cost} XP)`;
  };

  return (
    <Card data-testid="durance-card">
      <CardHeader>
        <CardTitle className="text-base">Durance</CardTitle>
        {status && (
          <CardDescription>
            Level {status.level}, seeking {status.target_level}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load Durance status.</p>}

        {status?.is_tier_boundary && (
          <p className="text-sm" data-testid="durance-tier-boundary">
            Your next step crosses a tier — that is Audere Majora, the Crossing, not the Durance.
          </p>
        )}

        {status && !status.is_tier_boundary && (
          <>
            {status.unlock_gate === null ? (
              <p className="text-sm text-muted-foreground" data-testid="durance-no-unlock-gate">
                No advancement is authored yet.
              </p>
            ) : (
              <div className="space-y-1 rounded-lg border p-3" data-testid="durance-unlock-gate">
                {status.unlock_gate.ready ? (
                  <p className="font-medium text-green-600" data-testid="durance-ready">
                    Ready to advance to level {status.target_level}.
                  </p>
                ) : (
                  <>
                    <p className="font-medium">Not yet ready:</p>
                    {status.unlock_gate.failed_requirements.map((reason) => (
                      <p key={reason} className="text-sm text-muted-foreground">
                        — {reason}
                      </p>
                    ))}
                  </>
                )}
                <p className="text-sm text-muted-foreground">
                  XP unlock: {renderUnlockStatus(status.unlock_gate)}
                </p>
              </div>
            )}

            {status.eligible_paths.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm font-medium">Eligible paths at this stage</p>
                <div className="flex flex-wrap gap-1.5">
                  {status.eligible_paths.map((p) => (
                    <Button
                      key={p.id}
                      variant={p.id === declaredPathId ? 'default' : 'outline'}
                      size="sm"
                      disabled={declareIntent.isPending}
                      onClick={() => declareIntent.mutate({ characterId, pathId: p.id })}
                      data-testid={`durance-path-${p.id}`}
                    >
                      {p.name}
                      {p.id === declaredPathId && ' (declared)'}
                    </Button>
                  ))}
                  {declaredPathId !== null && (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={clearIntent.isPending}
                      onClick={() => clearIntent.mutate(characterId)}
                      data-testid="durance-clear-intent"
                    >
                      Clear
                    </Button>
                  )}
                </div>
              </div>
            )}

            <p className="text-sm text-muted-foreground" data-testid="durance-site-status">
              {status.site_present ? 'A Durance training site is here.' : 'No training site here.'}
            </p>

            {openSessionId === null ? (
              <Button
                disabled={!status.site_present || convene.isPending}
                onClick={handleConvene}
                data-testid="durance-convene-button"
              >
                {convene.isPending ? 'Convening…' : 'Convene the Durance'}
              </Button>
            ) : (
              <div className="space-y-2 rounded-lg border border-dashed p-3">
                <p className="text-sm">
                  One stands before us in Durance. Speak thy name and testament.
                </p>
                <Textarea
                  placeholder="Your testament…"
                  value={testament}
                  onChange={(e) => setTestament(e.target.value)}
                  data-testid="durance-testament-input"
                />
                <Button
                  size="sm"
                  disabled={testament.trim() === '' || join.isPending}
                  onClick={handleJoin}
                  data-testid="durance-join-button"
                >
                  {join.isPending ? 'Speaking…' : 'Speak & Join'}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
