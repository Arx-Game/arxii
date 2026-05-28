import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swords, Zap, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { fetchAvailableActions, createActionRequest } from '../actionQueries';
import { fetchScene, sceneKeys } from '../queries';
import type { PlayerAction, AvailableEnhancement } from '../actionTypes';
import type { SceneDetail, SceneParticipant } from '../types';
import { SoulfrayWarning } from './SoulfrayWarning';
import { StrainSlider } from './StrainSlider';
import { TargetPicker, type TargetCandidate } from './TargetPicker';

interface Props {
  sceneId: string;
}

interface PendingWarning {
  enhancement: AvailableEnhancement;
  actionKey: string;
  techniqueId: number;
}

/**
 * Bottom-right floating action panel.  Reads the unified availability endpoint
 * and renders each PlayerAction with optional enhancement list, strain slider,
 * and target picker — all sourced from inline fields on the action.
 */
export function ActionPanel({ sceneId }: Props) {
  const [open, setOpen] = useState(false);
  const [expandedAction, setExpandedAction] = useState<string | null>(null);
  const [pendingWarning, setPendingWarning] = useState<PendingWarning | null>(null);
  const [targetingAction, setTargetingAction] = useState<PlayerAction | null>(null);
  // Per-action strain commitment — keyed by the action's stable display key.
  const [strainByAction, setStrainByAction] = useState<Record<string, number>>({});
  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk.
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

  // Scene participants — used as candidates when a targeted action is selected.
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(sceneId),
    enabled: open,
  });

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id?: number;
      technique_id?: number;
      strain_commitment?: number;
    }) => createActionRequest(sceneId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      setOpen(false);
      setTargetingAction(null);
      setStrainByAction({});
    },
  });

  // ------------------------------------------------------------------------
  // Stable key helpers
  // ------------------------------------------------------------------------

  function actionKeyFor(action: PlayerAction): string {
    return action.action_template?.name.toLowerCase() ?? action.display_name.toLowerCase();
  }

  function stableId(action: PlayerAction): string {
    return [
      action.ref.backend,
      action.ref.challenge_instance_id ?? '',
      action.ref.approach_id ?? '',
      action.ref.registry_key ?? '',
    ].join('-');
  }

  // ------------------------------------------------------------------------
  // Action invocation flow
  // ------------------------------------------------------------------------

  function commitAction(
    action: PlayerAction,
    extras: { target_persona_id?: number; technique_id?: number } = {}
  ) {
    const key = stableId(action);
    const strain = strainByAction[key];
    performAction.mutate({
      action_key: action.ref.registry_key ?? action.display_name,
      technique_id: extras.technique_id ?? action.ref.technique_id ?? undefined,
      target_persona_id: extras.target_persona_id,
      strain_commitment: strain && strain > 0 ? strain : undefined,
    });
  }

  function handleActionClick(action: PlayerAction) {
    // Targeted actions: open the picker.  Non-targeted: commit immediately.
    if (action.target_spec !== null) {
      setTargetingAction(action);
    } else {
      commitAction(action);
    }
  }

  function handleEnhancementClick(action: PlayerAction, enhancement: AvailableEnhancement) {
    if (enhancement.soulfray_warning) {
      setPendingWarning({
        enhancement,
        actionKey: action.ref.registry_key ?? actionKeyFor(action),
        techniqueId: enhancement.technique_id,
      });
    } else {
      commitAction(action, { technique_id: enhancement.technique_id });
    }
  }

  function handleWarningConfirm() {
    if (!pendingWarning) return;
    performAction.mutate({
      action_key: pendingWarning.actionKey,
      technique_id: pendingWarning.techniqueId,
    });
    setPendingWarning(null);
  }

  function handleWarningCancel() {
    setPendingWarning(null);
  }

  function toggleEnhancements(actionKey: string) {
    setExpandedAction((prev) => (prev === actionKey ? null : actionKey));
  }

  function handleStrainChange(action: PlayerAction, value: number) {
    setStrainByAction((prev) => ({ ...prev, [stableId(action)]: value }));
  }

  function handleTargetConfirm(ids: number[]) {
    if (!targetingAction || ids.length === 0) return;
    // The non-clash backend currently accepts a single target_persona; with
    // multi-cardinality specs we send the first id.  When the backend grows
    // multi-target support this path will fan out to a separate endpoint.
    commitAction(targetingAction, { target_persona_id: ids[0] });
    setTargetingAction(null);
  }

  function handleTargetCancel() {
    setTargetingAction(null);
  }

  // ------------------------------------------------------------------------
  // Target candidates from scene participants
  // ------------------------------------------------------------------------

  const candidates: TargetCandidate[] = useMemo(() => {
    const participants: SceneParticipant[] = scene?.participants ?? [];
    return participants.map((p) => ({ id: p.id, name: p.name }));
  }, [scene]);

  // ------------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------------

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button size="icon" className="h-12 w-12 rounded-full shadow-lg">
            <Swords className="h-5 w-5" />
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" align="end" className="w-80">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold">Actions</h3>

            {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}

            {data && data.results.length > 0 && (
              <div className="space-y-1.5">
                {data.results.map((action) => {
                  const actionKey = actionKeyFor(action);
                  const hasEnhancements = action.enhancements.length > 0;
                  const isExpanded = expandedAction === actionKey;
                  const hasStrain = action.strain !== null && action.strain.cap > 0;
                  const stable = stableId(action);
                  const strainValue = strainByAction[stable] ?? 0;
                  return (
                    <div key={stable}>
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant={action.prerequisite_met ? 'outline' : 'ghost'}
                          onClick={() => handleActionClick(action)}
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
                      {isExpanded && hasEnhancements && (
                        <div className="ml-2 mt-1 space-y-1 border-l border-muted pl-2">
                          {action.enhancements.map((enh) => {
                            const costLabel =
                              enh.effective_cost === 0 ? 'Free' : `${enh.effective_cost} anima`;
                            return (
                              <button
                                key={enh.technique_id}
                                onClick={() => handleEnhancementClick(action, enh)}
                                disabled={performAction.isPending}
                                className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-muted/50 disabled:opacity-50"
                              >
                                <span className="font-medium">{enh.technique_name}</span>
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
                      {hasStrain && action.strain && (
                        <div className="ml-2 mt-2 border-l border-muted pl-2">
                          <StrainSlider
                            value={strainValue}
                            cap={action.strain.cap}
                            baseEffectiveCost={0}
                            onChange={(v) => handleStrainChange(action, v)}
                          />
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

      {targetingAction && targetingAction.target_spec && (
        <TargetPicker
          spec={targetingAction.target_spec}
          candidates={candidates}
          onConfirm={handleTargetConfirm}
          onCancel={handleTargetCancel}
        />
      )}
    </div>
  );
}
