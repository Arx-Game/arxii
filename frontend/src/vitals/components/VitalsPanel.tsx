/**
 * VitalsPanel — read-only vitals on the character sheet (#521).
 *
 * Health + wound description, derived life status, anima, and the three
 * fatigue pools (reusing FatigueDisplay). Data is owner/staff-gated by
 * /api/vitals/<id>/ — when the query yields null (403/404), the panel
 * renders nothing, so unauthorized viewers see no vitals section at all.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useCharacterAnima } from '@/magic/queries';
import { FatigueDisplay } from '@/fatigue/components/FatigueDisplay';
import { useCharacterVitalsQuery } from '../vitalsQueries';
import type { CharacterStatus } from '../vitalsQueries';

const STATUS_BADGE_CLASSES: Record<CharacterStatus, string> = {
  alive: 'bg-green-100 text-green-800 border-green-300',
  dying: 'bg-red-100 text-red-800 border-red-300',
  incapacitated: 'bg-amber-100 text-amber-800 border-amber-300',
  dead: 'bg-slate-200 text-slate-700 border-slate-400',
};

interface BarProps {
  label: string;
  current: number;
  maximum: number;
  fillClass: string;
  note?: string;
  testId: string;
}

function VitalBar({ label, current, maximum, fillClass, note, testId }: BarProps) {
  const pct = maximum > 0 ? Math.max(0, Math.min(100, (current / maximum) * 100)) : 0;
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {current}/{maximum}
        </span>
      </div>
      <Progress value={pct} className="h-2" indicatorClassName={fillClass} />
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function VitalsPanel({ characterId }: { characterId: number }) {
  const { data: vitals } = useCharacterVitalsQuery(characterId);
  const { data: anima } = useCharacterAnima(characterId);

  if (!vitals) return null;

  const isWounded = vitals.max_health > 0 && vitals.health / vitals.max_health < 0.5;

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
        <VitalBar
          label="Health"
          current={vitals.health}
          maximum={vitals.max_health}
          fillClass={isWounded ? 'bg-amber-500' : 'bg-emerald-500'}
          note={vitals.wound_description || undefined}
          testId="vitals-health"
        />
        {anima && (
          <VitalBar
            label="Anima"
            current={anima.current}
            maximum={anima.maximum}
            fillClass="bg-violet-500"
            testId="vitals-anima"
          />
        )}
        <FatigueDisplay status={vitals.fatigue} className="border-0 shadow-none" />
      </CardContent>
    </Card>
  );
}
