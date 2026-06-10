/**
 * VitalsPanel — read-only vitals on the character sheet (#521).
 *
 * Health + wound description, derived life status, anima, and the three
 * fatigue pools (reusing FatigueBars). Data is owner/staff-gated by
 * /api/vitals/<id>/ — when the query yields null (403/404), the panel
 * renders nothing, so unauthorized viewers see no vitals section at all.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { StatBar } from '@/components/character/StatBar';
import { cn } from '@/lib/utils';
import { useCharacterAnima } from '@/magic/queries';
import { FatigueBars } from '@/fatigue/components/FatigueBars';
import { useCharacterVitalsQuery } from '../vitalsQueries';
import type { CharacterStatus } from '../vitalsQueries';

const STATUS_BADGE_CLASSES: Record<CharacterStatus, string> = {
  alive: 'bg-green-100 text-green-800 border-green-300',
  dying: 'bg-red-100 text-red-800 border-red-300',
  incapacitated: 'bg-amber-100 text-amber-800 border-amber-300',
  dead: 'bg-slate-200 text-slate-700 border-slate-400',
};

export function VitalsPanel({ characterId }: { characterId: number }) {
  const { data: vitals, isLoading } = useCharacterVitalsQuery(characterId);
  const { data: anima } = useCharacterAnima(characterId);

  if (isLoading) {
    return (
      <Card data-testid="vitals-panel-loading">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Vitals</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-2 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!vitals) return null;

  const isWounded = vitals.health_percentage < 0.5;

  return (
    <Card data-testid="vitals-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Vitals</CardTitle>
          <Badge
            variant="outline"
            className={cn('capitalize', STATUS_BADGE_CLASSES[vitals.status])}
          >
            {vitals.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <StatBar
          label="Health"
          valueText={`${vitals.health}/${vitals.max_health}`}
          percent={vitals.health_percentage * 100}
          fillClass={isWounded ? 'bg-amber-500' : 'bg-emerald-500'}
          note={vitals.wound_description || undefined}
          testId="vitals-health"
        />
        {anima && (
          <StatBar
            label="Anima"
            valueText={`${anima.current}/${anima.maximum}`}
            percent={anima.maximum > 0 ? (anima.current / anima.maximum) * 100 : 0}
            fillClass="bg-violet-500"
            testId="vitals-anima"
          />
        )}
        <FatigueBars status={vitals.fatigue} />
      </CardContent>
    </Card>
  );
}
