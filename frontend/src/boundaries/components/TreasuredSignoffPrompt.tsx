/**
 * TreasuredSignoffPrompt — pre-scene sign-off prompt (#1771).
 *
 * A treasured subject "requires signoff" for a beat when the viewer owns it
 * (via `tenureId`) and has no active `TreasuredSignoff` for that beat yet.
 * Renders nothing when the tenure has no treasured subjects at all. Grants
 * are explicit opt-in (never assumed); an existing grant can be withdrawn,
 * which re-opens the gate (mirrors `world.stories.services.boundaries`'
 * grant/withdraw semantics).
 */

import { ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  useTreasuredSubjects,
  useTreasuredSignoffs,
  useGrantTreasuredSignoff,
  useWithdrawTreasuredSignoff,
} from '../queries';

interface Props {
  beatId: number;
  tenureId: number;
}

export function TreasuredSignoffPrompt({ beatId, tenureId }: Props) {
  const { data: subjectsData } = useTreasuredSubjects(tenureId);
  const { data: signoffsData } = useTreasuredSignoffs({ beat: beatId });

  const grant = useGrantTreasuredSignoff();
  const withdraw = useWithdrawTreasuredSignoff();

  const subjects = subjectsData?.results ?? [];
  if (subjects.length === 0) {
    return null;
  }

  const signoffs = signoffsData?.results ?? [];
  const activeSignoffBySubject = new Map(
    signoffs.filter((s) => s.active).map((s) => [s.treasured_subject, s])
  );

  return (
    <Card className="border-amber-500/50 bg-amber-50 dark:bg-amber-950/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4" />
          Pre-scene sign-offs
        </CardTitle>
        <CardDescription>
          These are things this character treasures. Sign off to allow them to be staked in this
          beat — you can withdraw at any time before the scene resolves.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {subjects.map((subject) => {
          const activeSignoff = activeSignoffBySubject.get(subject.id);
          return (
            <div
              key={subject.id}
              className="flex items-center justify-between gap-3 rounded-md border bg-card px-3 py-2"
            >
              <span className="text-sm font-medium">{subject.subject_label}</span>
              {activeSignoff ? (
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Signed off</Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={withdraw.isPending}
                    onClick={() => withdraw.mutate({ id: activeSignoff.id, beat: beatId })}
                  >
                    Withdraw
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  disabled={grant.isPending}
                  onClick={() => grant.mutate({ beat: beatId, treasured_subject: subject.id })}
                >
                  Sign off
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
