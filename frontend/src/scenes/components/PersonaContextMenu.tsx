import { type ReactNode, useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Zap } from 'lucide-react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { createActionRequest } from '../actionQueries';
import type { ActionAttachmentInfo, PlayerActionsResponse, PlayerAction } from '../actionTypes';

interface Props {
  personaId: number;
  personaName: string;
  sceneId: string;
  children: ReactNode;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

export function PersonaContextMenu({
  personaId,
  personaName,
  sceneId,
  children,
  onAttachAction,
}: Props) {
  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk to look up
  // the correct cache key (which ActionAttachment populates as ['available-actions', characterId]).
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  // Read from React Query cache instead of triggering a fetch.
  // The ActionAttachment component populates this cache when opened.
  const data = queryClient.getQueryData<PlayerActionsResponse>(['available-actions', characterId]);

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id: number;
      technique_id?: number;
    }) => createActionRequest(sceneId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
  });

  // Show all prerequisite-met actions as potential targeted actions.
  const targetedActions: PlayerAction[] = (data?.results ?? []).filter((a) => a.prerequisite_met);

  if (targetedActions.length === 0) {
    return <>{children}</>;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="cursor-pointer font-medium hover:underline">{children}</button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Actions on {personaName}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {/* Direct execute: fires the action immediately via REST, independent of
            any pose in the composer. This is a "quick action" path. */}
        {targetedActions.map((action) => {
          const techniqueId = action.ref.technique_id ?? undefined;
          const actionKey =
            action.ref.registry_key ??
            action.action_template?.name.toLowerCase() ??
            action.display_name.toLowerCase();
          return (
            <DropdownMenuItem
              key={`${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`}
              disabled={performAction.isPending}
              onClick={() =>
                performAction.mutate({
                  action_key: actionKey,
                  target_persona_id: personaId,
                  technique_id: techniqueId,
                })
              }
            >
              <Zap className="mr-2 h-4 w-4" />
              {action.display_name}
            </DropdownMenuItem>
          );
        })}
        {/* Attach to Pose: stores the action in the composer so it is submitted
            alongside the next pose. Visually separated from the direct execute items. */}
        {onAttachAction && targetedActions.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs">Attach to Pose</DropdownMenuLabel>
            {targetedActions.map((action) => {
              const techniqueId = action.ref.technique_id ?? undefined;
              const actionKey =
                action.ref.registry_key ??
                action.action_template?.name.toLowerCase() ??
                action.display_name.toLowerCase();
              return (
                <DropdownMenuItem
                  key={`attach-${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`}
                  onClick={() =>
                    onAttachAction({
                      actionKey,
                      name: action.display_name,
                      target: personaName,
                      requiresTarget: true,
                      techniqueId,
                      targetPersonaId: personaId,
                    })
                  }
                >
                  <Zap className="mr-2 h-4 w-4" />
                  {action.display_name}
                </DropdownMenuItem>
              );
            })}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
