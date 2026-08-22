/**
 * CheckCallPromptCard — the one-tap answer surface for a GM's `CheckCall` (#3295).
 *
 * Polls the requesting player's own pending check-call prompt(s)
 * (`useMyCheckCalls`, `GET /api/checks/check-call-targets/`) and renders each
 * as a card with Answer/Decline buttons dispatching `answer_check_call`/
 * `decline_check_call` (`actions/definitions/scene_checks.py`) — the SAME
 * bound catalog check + band the GM called, never a free pick. Answering
 * broadcasts the roll to the room via the scene pipeline; declining is quiet
 * (no mechanical force, no broadcast) — mirrors `SummonPromptNotifier.tsx`'s
 * shape for a GM-initiated prompt.
 */

import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMemo } from 'react';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import type { DispatchResult } from '@/combat/types';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useMyCheckCalls, sceneCheckKeys } from '@/checks/queries';
import type { CheckCallTargetEntry } from '@/checks/types';

function reportResult(result: DispatchResult, fallbackSuccess: string): void {
  if (isDispatchFailure(result)) {
    toast.error(result.message ?? 'That call could not be answered.');
    return;
  }
  toast.success(result.message ?? fallbackSuccess);
}

function CheckCallRow({ call, characterId }: { call: CheckCallTargetEntry; characterId: number }) {
  const dispatch = useDispatchPlayerAction(characterId);
  const queryClient = useQueryClient();

  function respond(registryKey: 'answer_check_call' | 'decline_check_call', successMsg: string) {
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: registryKey },
        kwargs: { call_id: call.call_id },
      })
      .then((result) => {
        reportResult(result, successMsg);
        queryClient.invalidateQueries({ queryKey: sceneCheckKeys.myCheckCalls() });
      })
      .catch(() => toast.error('Could not respond to that call.'));
  }

  return (
    <div className="space-y-2 rounded-md border p-3" data-testid="check-call-prompt-row">
      <p className="text-sm">
        <span className="font-medium">{call.caller_display_name}</span> calls for a check:{' '}
        <span className="font-medium">{call.check_type_name}</span> ({call.band_label})
      </p>
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={dispatch.isPending}
          onClick={() => respond('answer_check_call', 'Check rolled.')}
          data-testid="check-call-answer"
        >
          Answer
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={dispatch.isPending}
          onClick={() => respond('decline_check_call', 'Declined.')}
          data-testid="check-call-decline"
        >
          Decline
        </Button>
      </div>
    </div>
  );
}

interface CheckCallPromptCardProps {
  className?: string;
}

export function CheckCallPromptCard({ className }: CheckCallPromptCardProps) {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const { data: calls = [] } = useMyCheckCalls({ enabled: characterId !== null });

  if (characterId === null || calls.length === 0) {
    return null;
  }

  return (
    <Card className={className} data-testid="check-call-prompt-card">
      <CardHeader>
        <CardTitle className="text-base">Check Called</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {calls.map((call) => (
          <CheckCallRow key={call.id} call={call} characterId={characterId} />
        ))}
      </CardContent>
    </Card>
  );
}
