import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchPendingRequests, respondToRequest } from '../actionQueries';
import type { ActionRequest } from '../actionTypes';

interface Props {
  sceneId: string;
}

const DIFFICULTY_OPTIONS = [
  { label: 'Easy', value: 'easy' },
  { label: 'Standard', value: 'standard' },
  { label: 'Hard', value: 'hard' },
] as const;

export function ConsentPrompt({ sceneId }: Props) {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ['pending-requests', sceneId],
    queryFn: () => fetchPendingRequests(sceneId),
    refetchInterval: 5_000,
  });

  const respond = useMutation({
    mutationFn: ({
      requestId,
      accept,
      difficulty,
    }: {
      requestId: number;
      accept: boolean;
      difficulty?: string;
    }) => respondToRequest(sceneId, requestId, { accept, difficulty }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
    },
  });

  const requests = data?.results ?? [];

  if (requests.length === 0) return null;

  return (
    <div className="space-y-2">
      {requests.map((req: ActionRequest) => (
        <div
          key={req.id}
          className="flex items-center gap-3 rounded-md border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30"
        >
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              <span className="font-semibold">{req.initiator_persona.name}</span> wants to use{' '}
              <span className="font-semibold">
                {req.action_name}
                {req.technique_name ? ` (${req.technique_name})` : ''}
              </span>{' '}
              on your character.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => respond.mutate({ requestId: req.id, accept: false })}
              disabled={respond.isPending}
            >
              <X className="mr-1 h-3.5 w-3.5" />
              Deny
            </Button>
            {DIFFICULTY_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                size="sm"
                variant="secondary"
                onClick={() =>
                  respond.mutate({
                    requestId: req.id,
                    accept: true,
                    difficulty: opt.value,
                  })
                }
                disabled={respond.isPending}
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                {opt.label}
              </Button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
