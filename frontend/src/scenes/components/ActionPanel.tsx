import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Swords, Zap, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { fetchAvailableActions, fetchSceneActions, createActionRequest } from '../actionQueries';
import type { PlayerAction, AvailableEnhancement, AvailableSceneAction } from '../actionTypes';
import { SoulfrayWarning } from './SoulfrayWarning';

interface Props {
  sceneId: string;
}

interface PendingWarning {
  enhancement: AvailableEnhancement;
  actionKey: string;
}

export function ActionPanel({ sceneId }: Props) {
  const [open, setOpen] = useState(false);
  const [selectingTarget, setSelectingTarget] = useState<PlayerAction | null>(null);
  const [expandedAction, setExpandedAction] = useState<string | null>(null);
  const [pendingWarning, setPendingWarning] = useState<PendingWarning | null>(null);
  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk.
  // Follows the same pattern as FocusPanel and ThreadHubPage.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const { data, isLoading } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: open && characterId !== null,
  });

  const { data: sceneActions } = useQuery({
    queryKey: ['scene-actions', sceneId],
    queryFn: () => fetchSceneActions(sceneId),
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

  function handleSelfAction(action: PlayerAction) {
    const techniqueId = action.ref.technique_id ?? undefined;
    performAction.mutate({
      action_key: action.ref.registry_key ?? action.display_name,
      technique_id: techniqueId,
    });
  }

  function handleTargetedAction(action: PlayerAction) {
    setSelectingTarget(action);
  }

  function handleEnhancementClick(actionKey: string, enhancement: AvailableEnhancement) {
    if (enhancement.soulfray_warning) {
      setPendingWarning({ enhancement, actionKey });
    } else {
      performAction.mutate({ action_key: actionKey, technique_id: enhancement.technique_id });
    }
  }

  function handleWarningConfirm() {
    if (!pendingWarning) return;
    performAction.mutate({
      action_key: pendingWarning.actionKey,
      technique_id: pendingWarning.enhancement.technique_id,
    });
    setPendingWarning(null);
  }

  function handleWarningCancel() {
    setPendingWarning(null);
  }

  function toggleEnhancements(actionKey: string) {
    setExpandedAction((prev) => (prev === actionKey ? null : actionKey));
  }

  if (selectingTarget) {
    return (
      <div className="fixed bottom-6 right-6 z-50">
        <div className="rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg">
          <p className="mb-2 text-sm font-medium">
            Select a target for: {selectingTarget.display_name}
          </p>
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

            {data && data.results.length > 0 && (
              <div className="space-y-1.5">
                {data.results.map((action) => {
                  // Social-action panel: look up enhancement data from the scene-actions
                  // endpoint (fetchSceneActions), which carries the richer enhancement
                  // payload (anima costs, Soulfray warnings).  The action_template name
                  // is used as the join key since the scene-actions endpoint uses the
                  // template name lowercased as the action_key.
                  const actionKey =
                    action.action_template?.name.toLowerCase() ?? action.display_name.toLowerCase();
                  const sceneAction: AvailableSceneAction | undefined = sceneActions?.find(
                    (sa) => sa.action_key === actionKey
                  );
                  const hasEnhancements =
                    sceneAction !== undefined && sceneAction.enhancements.length > 0;
                  const isExpanded = expandedAction === actionKey;
                  return (
                    <div
                      key={`${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`}
                    >
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant={action.prerequisite_met ? 'outline' : 'ghost'}
                          onClick={() =>
                            action.prerequisite_met
                              ? handleSelfAction(action)
                              : handleTargetedAction(action)
                          }
                          disabled={performAction.isPending || !action.prerequisite_met}
                          className="flex-1"
                          title={action.prerequisite_reasons.join('; ') || undefined}
                        >
                          <Zap className="mr-1 h-3.5 w-3.5" />
                          {action.display_name}
                          {action.difficulty && (
                            <span className="ml-1 text-xs text-muted-foreground">
                              ({action.difficulty})
                            </span>
                          )}
                        </Button>
                        {hasEnhancements && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => toggleEnhancements(actionKey)}
                            disabled={performAction.isPending}
                            className="px-1.5"
                            title="Show enhancements"
                          >
                            {isExpanded ? (
                              <ChevronUp className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        )}
                      </div>
                      {isExpanded && sceneAction && (
                        <div className="ml-2 mt-1 space-y-1 border-l border-muted pl-2">
                          {sceneAction.enhancements.map((enh) => {
                            const costLabel =
                              enh.effective_cost === 0 ? 'Free' : `${enh.effective_cost} anima`;
                            return (
                              <button
                                key={enh.technique_id}
                                onClick={() => handleEnhancementClick(actionKey, enh)}
                                disabled={performAction.isPending}
                                className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-muted/50 disabled:opacity-50"
                              >
                                <span className="font-medium">{enh.variant_name}</span>
                                <span className="ml-2 flex items-center gap-1 text-muted-foreground">
                                  {enh.soulfray_warning && (
                                    <AlertTriangle className="h-3 w-3 text-amber-400" />
                                  )}
                                  {costLabel}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {data && data.results.length === 0 && (
              <p className="text-sm text-muted-foreground">No actions available.</p>
            )}

            {pendingWarning && (
              <SoulfrayWarning
                warning={pendingWarning.enhancement.soulfray_warning!}
                techniqueName={pendingWarning.enhancement.technique_name}
                animaCost={pendingWarning.enhancement.effective_cost}
                onConfirm={handleWarningConfirm}
                onCancel={handleWarningCancel}
              />
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
