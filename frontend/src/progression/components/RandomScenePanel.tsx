/**
 * RandomScenePanel - displays weekly random scene targets with claim/reroll actions.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, RefreshCw, Users } from 'lucide-react';
import { toast } from 'sonner';
import {
  useRandomSceneTargetsQuery,
  useClaimTargetMutation,
  useRerollTargetMutation,
} from '../randomSceneQueries';

export function RandomScenePanel() {
  const { data: targets, isLoading, error } = useRandomSceneTargetsQuery();
  const claimMutation = useClaimTargetMutation();
  const rerollMutation = useRerollTargetMutation();

  const claimedCount = targets?.filter((t) => t.claimed).length ?? 0;
  const totalCount = targets?.length ?? 0;
  const anyRerolled = targets?.some((t) => t.rerolled) ?? false;

  function handleClaim(targetId: number) {
    claimMutation.mutate(targetId, {
      onSuccess: () => toast.success('Target claimed!'),
      onError: (err) => toast.error(err.message),
    });
  }

  function handleReroll(targetId: number) {
    rerollMutation.mutate(targetId, {
      onSuccess: () => toast.success('Target rerolled!'),
      onError: (err) => toast.error(err.message),
    });
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4" />
            Random Scene Targets
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading targets...</p>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4" />
            Random Scene Targets
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">Failed to load targets.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Random Scene Targets
          </span>
          <span className="text-sm font-normal text-muted-foreground">
            Claimed: {claimedCount}/{totalCount}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {targets && targets.length === 0 && (
          <p className="text-sm text-muted-foreground">No targets assigned this week.</p>
        )}
        {targets?.map((target) => {
          const isClaimingThis = claimMutation.isPending && claimMutation.variables === target.id;
          return (
            <div
              key={target.id}
              className="flex items-center justify-between rounded-lg border p-3"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">#{target.slot_number}</span>
                <span className="text-sm font-medium">{target.target_persona_name}</span>
                {target.first_time && (
                  <Badge variant="secondary" className="text-xs">
                    First time!
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-1">
                {!target.claimed && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={anyRerolled || rerollMutation.isPending}
                    onClick={() => handleReroll(target.id)}
                    title="Reroll this target"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                )}
                <Button
                  variant={target.claimed ? 'ghost' : 'default'}
                  size="sm"
                  disabled={target.claimed || isClaimingThis}
                  onClick={() => handleClaim(target.id)}
                  title={target.claimed ? 'Already claimed' : 'Claim this target'}
                >
                  {target.claimed ? (
                    <Check className="h-3.5 w-3.5 text-green-500" />
                  ) : isClaimingThis ? (
                    'Claiming...'
                  ) : (
                    'Claim'
                  )}
                </Button>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
