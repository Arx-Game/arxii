/**
 * PrecapturePanel — the scene starter's truncate/cutoff control (#3069 sub-item 4).
 *
 * Lists the scene's pre-scene-captured poses (recorded before the scene started, then
 * folded in on scene start or a later consent accept) oldest first, each with a
 * "Start scene from here" button that drops everything captured before it. Only
 * rendered for the scene owner (mirrors `IsSceneOwnerOrStaff`/`TruncatePrecaptureAction`'s
 * gate); a live in-scene pose is never in this list (see `list_precaptured`'s
 * timestamp-before-`date_started` invariant on the backend), so there is nothing here
 * to accidentally truncate away.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Scissors } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchPrecapturedInteractions, truncatePrecapture } from '../precaptureQueries';

interface Props {
  sceneId: string;
}

export function PrecapturePanel({ sceneId }: Props) {
  const queryClient = useQueryClient();

  const { data: captured = [] } = useQuery({
    queryKey: ['precaptured-interactions', sceneId],
    queryFn: () => fetchPrecapturedInteractions(sceneId),
  });

  const truncate = useMutation({
    mutationFn: (interactionId: number) => truncatePrecapture(sceneId, interactionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['precaptured-interactions', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
    },
  });

  if (captured.length === 0) return null;

  return (
    <div
      className="space-y-2 rounded-md border border-muted-foreground/20 bg-muted/30 p-3"
      data-testid="precapture-panel"
    >
      <p className="text-xs font-semibold text-muted-foreground">
        Captured from before this scene started — pick where it should really begin:
      </p>
      <ul className="space-y-1">
        {captured.map((interaction) => (
          <li
            key={interaction.id}
            className="flex items-center justify-between gap-2 text-sm"
            data-testid="precapture-row"
          >
            <span className="truncate">
              <span className="font-semibold">{interaction.persona_name}:</span>{' '}
              {interaction.content}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={truncate.isPending}
              onClick={() => truncate.mutate(interaction.id)}
              data-testid="precapture-truncate-btn"
            >
              <Scissors className="mr-1 h-3.5 w-3.5" />
              Start scene from here
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
