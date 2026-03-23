import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Swords,
  Sparkles,
  User,
  Handshake,
  ShieldAlert,
  Heart,
  Eye,
  Drama,
  Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { fetchAvailableActions, createActionRequest } from '../actionQueries';
import type { AvailableAction, TechniqueAction } from '../actionTypes';

interface Props {
  sceneId: string;
}

const ICON_MAP: Record<string, LucideIcon> = {
  swords: Swords,
  sparkles: Sparkles,
  user: User,
  handshake: Handshake,
  shield_alert: ShieldAlert,
  heart: Heart,
  eye: Eye,
  drama: Drama,
  zap: Zap,
};

function getIcon(iconName: string): LucideIcon {
  return ICON_MAP[iconName] ?? Zap;
}

export function ActionPanel({ sceneId }: Props) {
  const [open, setOpen] = useState(false);
  const [selectingTarget, setSelectingTarget] = useState<AvailableAction | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['available-actions', sceneId],
    queryFn: () => fetchAvailableActions(sceneId),
    enabled: open,
  });

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id?: number;
      technique_id?: number;
    }) => createActionRequest(sceneId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      setOpen(false);
      setSelectingTarget(null);
    },
  });

  function handleSelfAction(action: AvailableAction) {
    const techniqueId = action.techniques.length > 0 ? action.techniques[0].id : undefined;
    performAction.mutate({ action_key: action.key, technique_id: techniqueId });
  }

  function handleTargetedAction(action: AvailableAction) {
    setSelectingTarget(action);
  }

  function handleTechniqueAction(action: TechniqueAction) {
    performAction.mutate({
      action_key: `technique_${action.template_id}`,
      technique_id: action.technique_id,
    });
  }

  if (selectingTarget) {
    return (
      <div className="fixed bottom-6 right-6 z-50">
        <div className="rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg">
          <p className="mb-2 text-sm font-medium">Select a target for: {selectingTarget.name}</p>
          <p className="mb-3 text-xs text-muted-foreground">
            Right-click a character name in the scene to target them.
          </p>
          <Button size="sm" variant="outline" onClick={() => setSelectingTarget(null)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button size="icon" className="h-12 w-12 rounded-full shadow-lg">
            <Swords className="h-5 w-5" />
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" align="end" className="w-72">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold">Actions</h3>

            {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}

            {data && data.self_actions.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase text-muted-foreground">
                  Your Actions
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {data.self_actions.map((action) => {
                    const Icon = getIcon(action.icon);
                    return (
                      <Button
                        key={action.key}
                        size="sm"
                        variant="outline"
                        onClick={() => handleSelfAction(action)}
                        disabled={performAction.isPending}
                      >
                        <Icon className="mr-1 h-3.5 w-3.5" />
                        {action.name}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}

            {data && data.targeted_actions.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase text-muted-foreground">
                  Social Actions
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {data.targeted_actions.map((action) => {
                    const Icon = getIcon(action.icon);
                    return (
                      <Button
                        key={action.key}
                        size="sm"
                        variant="outline"
                        onClick={() => handleTargetedAction(action)}
                        disabled={performAction.isPending}
                      >
                        <Icon className="mr-1 h-3.5 w-3.5" />
                        {action.name}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}

            {data && data.technique_actions.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase text-muted-foreground">
                  Techniques
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {data.technique_actions.map((action) => {
                    const Icon = getIcon(action.icon);
                    return (
                      <Button
                        key={`tech-${action.template_id}-${action.technique_id}`}
                        size="sm"
                        variant="outline"
                        onClick={() => handleTechniqueAction(action)}
                        disabled={performAction.isPending}
                      >
                        <Icon className="mr-1 h-3.5 w-3.5" />
                        {action.technique_name}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}

            {data &&
              data.self_actions.length === 0 &&
              data.targeted_actions.length === 0 &&
              data.technique_actions.length === 0 && (
                <p className="text-sm text-muted-foreground">No actions available.</p>
              )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
