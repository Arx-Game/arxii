import { type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Handshake, ShieldAlert, Heart, Eye, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { createActionRequest } from '../actionQueries';
import type { ActionAttachmentInfo } from '../actionTypes';
import type { AvailableActionsResponse } from '../actionTypes';

interface Props {
  personaId: number;
  personaName: string;
  sceneId: string;
  children: ReactNode;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

const ICON_MAP: Record<string, LucideIcon> = {
  handshake: Handshake,
  shield_alert: ShieldAlert,
  heart: Heart,
  eye: Eye,
  zap: Zap,
};

function getIcon(iconName: string): LucideIcon {
  return ICON_MAP[iconName] ?? Zap;
}

export function PersonaContextMenu({
  personaId,
  personaName,
  sceneId,
  children,
  onAttachAction,
}: Props) {
  const queryClient = useQueryClient();

  // Read from React Query cache instead of triggering a fetch.
  // The ActionAttachment component populates this cache when opened.
  const data = queryClient.getQueryData<AvailableActionsResponse>(['available-actions', sceneId]);

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

  const targetedActions = data?.targeted_actions ?? [];

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
          const Icon = getIcon(action.icon);
          const techniqueId =
            (action.applicable_techniques ?? action.techniques).length > 0
              ? (action.applicable_techniques ?? action.techniques)[0].id
              : undefined;
          return (
            <DropdownMenuItem
              key={action.key}
              disabled={performAction.isPending}
              onClick={() =>
                performAction.mutate({
                  action_key: action.key,
                  target_persona_id: personaId,
                  technique_id: techniqueId,
                })
              }
            >
              <Icon className="mr-2 h-4 w-4" />
              {action.name}
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
              const techniqueId =
                (action.applicable_techniques ?? action.techniques).length > 0
                  ? (action.applicable_techniques ?? action.techniques)[0].id
                  : undefined;
              return (
                <DropdownMenuItem
                  key={`attach-${action.key}`}
                  onClick={() =>
                    onAttachAction({
                      actionKey: action.key,
                      name: action.name,
                      target: personaName,
                      requiresTarget: true,
                      techniqueId,
                      targetPersonaId: personaId,
                    })
                  }
                >
                  <Zap className="mr-2 h-4 w-4" />
                  {action.name}
                </DropdownMenuItem>
              );
            })}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
