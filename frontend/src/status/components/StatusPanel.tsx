/**
 * StatusPanel — qualitative status card stack on the game rail's Status tab (#1446).
 *
 * DESIGN RULING: "The sheet describes; the scene does" — this panel is read-only
 * status; no spend/use buttons. Health, stamina (fatigue), and anima render as
 * WORDS only (wound description, fatigue zone names, anima band) — never the
 * numeric StatBar used on the character sheet. Coins and Action Points are
 * currencies, so numbers are fine for those two lines.
 *
 * Mirrors VitalsPanel's null-on-403/404 behavior: when the vitals query yields
 * null (viewer doesn't own this character), the whole panel renders nothing.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatCoppers } from '@/lib/currency';
import { useCharacterAnima, useCharacterResonances } from '@/magic/queries';
import { useCharacterVitalsQuery } from '@/vitals/vitalsQueries';
import type { CharacterStatus } from '@/vitals/vitalsQueries';
import { useActionPoints, useCharacterPurse } from '../queries';

const STATUS_BADGE_CLASSES: Record<CharacterStatus, string> = {
  alive: 'bg-green-100 text-green-800 border-green-300',
  dying: 'bg-red-100 text-red-800 border-red-300',
  incapacitated: 'bg-amber-100 text-amber-800 border-amber-300',
  dead: 'bg-slate-200 text-slate-700 border-slate-400',
};

const ZONE_BADGE_CLASSES: Record<string, string> = {
  fresh: 'bg-green-100 text-green-800 border-green-300',
  strained: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  tired: 'bg-orange-100 text-orange-800 border-orange-300',
  overexerted: 'bg-red-100 text-red-800 border-red-300',
  exhausted: 'bg-red-200 text-red-900 border-red-400',
};

const FATIGUE_POOL_LABELS = {
  physical: 'Physical',
  social: 'Social',
  mental: 'Mental',
} as const;

export function StatusPanel({ characterId }: { characterId: number }) {
  const { data: vitals, isLoading } = useCharacterVitalsQuery(characterId);
  const { data: anima } = useCharacterAnima(characterId);
  const { data: resonances = [] } = useCharacterResonances(characterId);
  const { data: purse } = useCharacterPurse(characterId);
  const { data: actionPoints } = useActionPoints(characterId);

  if (isLoading) {
    return (
      <Card data-testid="status-panel-loading">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!vitals) return null;

  // `band` is generated on CharacterAnima (#1446) but the hand-rolled
  // CharacterAnimaRecord interface in magic/api.ts predates it — extend
  // locally rather than editing a file outside this task's scope.
  const animaBand = (anima as { band?: string } | undefined)?.band;

  return (
    <Card data-testid="status-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Status</CardTitle>
          <Badge
            variant="outline"
            className={cn('capitalize', STATUS_BADGE_CLASSES[vitals.status])}
          >
            {vitals.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <section aria-label="Condition" className="space-y-1">
          <p className="text-sm text-muted-foreground">{vitals.wound_description || 'Unhurt.'}</p>
        </section>

        <section aria-label="Fatigue" className="space-y-2">
          <p className="text-sm font-medium">Fatigue</p>
          <div className="flex flex-wrap gap-2">
            {(['physical', 'social', 'mental'] as const).map((pool) => (
              <Badge
                key={pool}
                variant="outline"
                className={cn('text-xs capitalize', ZONE_BADGE_CLASSES[vitals.fatigue[pool].zone])}
              >
                {FATIGUE_POOL_LABELS[pool]}: {vitals.fatigue[pool].zone}
              </Badge>
            ))}
          </div>
        </section>

        {animaBand && (
          <section aria-label="Anima" className="space-y-1">
            <p className="text-sm font-medium">Anima</p>
            <Badge variant="outline" className="text-xs capitalize">
              {animaBand}
            </Badge>
          </section>
        )}

        <section aria-label="Resonances" className="space-y-1">
          <p className="text-sm font-medium">Resonances</p>
          {resonances.length === 0 ? (
            <p className="text-sm text-muted-foreground">No resonances yet.</p>
          ) : (
            <ul className="space-y-0.5 text-sm text-muted-foreground">
              {resonances.map((resonance) => (
                <li key={resonance.id}>{resonance.resonance_name}</li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Purse" className="space-y-1">
          <p className="text-sm font-medium">Coin</p>
          <p className="text-sm text-muted-foreground">
            {purse ? formatCoppers(purse.balance ?? 0) : 'Unknown.'}
          </p>
        </section>

        <section aria-label="Action Points" className="space-y-1">
          <p className="text-sm font-medium">Action Points</p>
          <p className="text-sm text-muted-foreground">
            {actionPoints ? (
              <>
                {actionPoints.current} of {actionPoints.effective_maximum} this week
                {actionPoints.banked > 0 && ` (+${actionPoints.banked} banked)`}
              </>
            ) : (
              'Unknown.'
            )}
          </p>
        </section>
      </CardContent>
    </Card>
  );
}
