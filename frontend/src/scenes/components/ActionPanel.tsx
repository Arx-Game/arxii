import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swords, Zap, AlertTriangle, ChevronDown, ChevronUp, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useAppSelector } from '@/store/hooks';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import {
  createActionRequest,
  castTechnique,
  useCastableTechniques,
  useAvailableActionsQuery,
  toastDispositionMessage,
} from '../actionQueries';
import { fetchScene, sceneKeys } from '../queries';
import { PowerLedgerPanel } from '@/magic/components/PowerLedgerPanel';
import { ThreadPullPicker } from '@/magic/components/threads/ThreadPullPicker';
import { useCastPullSelection } from '../hooks/useCastPullSelection';
import { extractErrorMessage } from '@/lib/errors';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { magicKeys } from '@/magic/queries';
import type {
  PlayerAction,
  AvailableEnhancement,
  BoonAskPayload,
  CastableTechnique,
  CastResponse,
  CastPullRequestBody,
} from '../actionTypes';
import type { SceneDetail, SceneParticipant } from '../types';
import { SoulfrayWarning } from './SoulfrayWarning';
import { StrainSlider } from './StrainSlider';
import { TargetPicker, type TargetCandidate } from './TargetPicker';
import { BoonAskForm } from './BoonAskForm';

interface Props {
  sceneId: string;
}

interface PendingWarning {
  enhancement: AvailableEnhancement;
  actionKey: string;
  techniqueId: number;
}

const EFFORT_OPTIONS = [
  { label: 'Very Low', value: 'very_low' },
  { label: 'Low', value: 'low' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
  { label: 'Extreme', value: 'extreme' },
] as const;

const DEFAULT_EFFORT = 'medium';

/**
 * Bottom-right floating action panel.  Reads the unified availability endpoint
 * and renders each PlayerAction with optional enhancement list, strain slider,
 * and target picker — all sourced from inline fields on the action.
 */
export function ActionPanel({ sceneId }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [expandedAction, setExpandedAction] = useState<string | null>(null);
  const [pendingWarning, setPendingWarning] = useState<PendingWarning | null>(null);
  const [targetingAction, setTargetingAction] = useState<PlayerAction | null>(null);
  // #2540: a boon dispatch held open while the asker specifies the structured ask.
  const [boonAskState, setBoonAskState] = useState<{
    action: PlayerAction;
    targetId: number;
  } | null>(null);
  // Per-action strain commitment — keyed by the action's stable display key.
  const [strainByAction, setStrainByAction] = useState<Record<string, number>>({});
  // Initiator effort level for social actions (#1275).
  const [effortLevel, setEffortLevel] = useState<string>(DEFAULT_EFFORT);

  // Cast section state
  const [castOpen, setCastOpen] = useState(false);
  const [selectedTechnique, setSelectedTechnique] = useState<CastableTechnique | null>(null);
  const [castTargetPersonaId, setCastTargetPersonaId] = useState<number | null>(null);
  /** Selected persona ids for FILTERED_GROUP multi-cast. */
  const [castTargetPersonaIds, setCastTargetPersonaIds] = useState<number[]>([]);
  const [castPickingTarget, setCastPickingTarget] = useState(false);
  const [castLedgerResult, setCastLedgerResult] = useState<CastResponse | null>(null);

  const queryClient = useQueryClient();

  // Shared by performCast and performAction's onSuccess — a cast or dispatched
  // action may have spent anima/resonance, so both invalidate the same set
  // of caches (#2158).
  function invalidateActionOutcomeQueries() {
    // 2026-07 audit: 'scene-messages' matched no query anywhere — the feed's
    // real key is 'scene-interactions' (useSceneInteractions).
    queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
    queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    if (characterId !== null) {
      queryClient.invalidateQueries({ queryKey: magicKeys.characterAnima(characterId) });
      queryClient.invalidateQueries({ queryKey: magicKeys.characterResonanceList() });
    }
  }

  // Resolve the active character name to its numeric ObjectDB pk and primary persona.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName) ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const characterId = activeEntry?.character_id ?? null;
  const initiatorPersonaId = actingPersonaId(activeEntry);

  const { data, isLoading } = useAvailableActionsQuery(characterId, { enabled: open });

  // Scene participants — used as candidates when a targeted action is selected.
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(sceneId),
    enabled: open,
  });

  // Castable techniques for the standalone cast flow.
  const { data: castableTechniques = [], isLoading: isCastLoading } = useCastableTechniques(
    open ? initiatorPersonaId : null
  );

  // Thread-pull selection hook — manages selectedPulls, pullNotice, pullsContext,
  // balanceByResonanceId, and payload assembly for the cast flow (#895).
  const pull = useCastPullSelection({
    selectedTechnique,
    characterId,
    castTargetPersonaId,
    sceneId,
    castOpen,
  });

  const performCast = useMutation({
    mutationFn: (params: {
      technique_id: number;
      target_persona?: number | null;
      target_persona_ids?: number[];
      strain_commitment?: number;
      pull?: CastPullRequestBody;
    }) =>
      castTechnique(sceneId, {
        initiator_persona: initiatorPersonaId!,
        ...params,
      }),
    onSuccess: (data) => {
      invalidateActionOutcomeQueries();
      setSelectedTechnique(null);
      setCastTargetPersonaId(null);
      setCastTargetPersonaIds([]);
      setCastPickingTarget(false);
      pull.reset();
      if (data.encounter) {
        toast.success('Combat has begun', {
          action: {
            label: 'Join Combat',
            // #2197: combat renders in-scene now, so this navigates to the
            // scene itself (a no-op when already there — this toast can also
            // fire from GamePage, where it's a real cross-page jump).
            onClick: () => navigate(`/scenes/${sceneId}`),
          },
        });
      }
      if (data.result?.power_ledger) {
        // Immediate cast: keep the panel open showing the ledger (#859).
        setCastLedgerResult(data);
      } else {
        setOpen(false);
        setCastOpen(false);
      }
    },
  });

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id?: number;
      /** Multi-target dispatch (#572). */
      target_persona_ids?: number[];
      technique_id?: number;
      strain_commitment?: number;
      effort_level?: string;
      /** Structured-ask payload (#2540) — boon dispatches only. */
      boon?: BoonAskPayload;
    }) => createActionRequest(sceneId, params),
    onSuccess: (data) => {
      invalidateActionOutcomeQueries();
      toastDispositionMessage(data);
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
    extras: {
      target_persona_id?: number;
      /** Multi-target dispatch (#572). */
      target_persona_ids?: number[];
      technique_id?: number;
      /** Structured-ask payload (#2540) — boon dispatches only. */
      boon?: BoonAskPayload;
    } = {}
  ) {
    const key = stableId(action);
    const strain = strainByAction[key];
    performAction.mutate({
      action_key: action.ref.registry_key ?? action.display_name,
      technique_id: extras.technique_id ?? action.ref.technique_id ?? undefined,
      ...(extras.target_persona_id !== undefined
        ? { target_persona_id: extras.target_persona_id }
        : {}),
      ...(extras.target_persona_ids !== undefined
        ? { target_persona_ids: extras.target_persona_ids }
        : {}),
      ...(extras.boon !== undefined ? { boon: extras.boon } : {}),
      strain_commitment: strain && strain > 0 ? strain : undefined,
      effort_level: effortLevel !== DEFAULT_EFFORT ? effortLevel : undefined,
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
      effort_level: effortLevel !== DEFAULT_EFFORT ? effortLevel : undefined,
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
    // #2540: a boon needs its structured ask specified before dispatch — hold the
    // action and open the ask form instead of committing on target pick.
    if ((targetingAction.ref.registry_key ?? '') === 'boon' && ids.length === 1) {
      setBoonAskState({ action: targetingAction, targetId: ids[0] });
      setTargetingAction(null);
      return;
    }
    commitAction(
      targetingAction,
      ids.length === 1 ? { target_persona_id: ids[0] } : { target_persona_ids: ids }
    );
    setTargetingAction(null);
  }

  function handleTargetCancel() {
    setTargetingAction(null);
  }

  function handleBoonConfirm(payload: BoonAskPayload) {
    if (!boonAskState) return;
    commitAction(boonAskState.action, {
      target_persona_id: boonAskState.targetId,
      boon: payload,
    });
    setBoonAskState(null);
  }

  // ------------------------------------------------------------------------
  // Cast flow handlers
  // ------------------------------------------------------------------------

  function handleTechniqueSelect(technique: CastableTechnique) {
    setSelectedTechnique(technique);
    setCastTargetPersonaId(null);
    setCastTargetPersonaIds([]);
    setCastLedgerResult(null);
    performCast.reset();
    pull.reset();
  }

  function handleCastCommit() {
    if (!selectedTechnique || initiatorPersonaId === null) return;
    const payload = pull.buildPullPayload();
    if ('error' in payload) {
      pull.setPullNotice(payload.error);
      return;
    }
    const cardinality = selectedTechnique.target_spec?.cardinality ?? selectedTechnique.target_type;
    if (cardinality === 'filtered_group') {
      performCast.mutate({
        technique_id: selectedTechnique.id,
        target_persona_ids: castTargetPersonaIds,
        ...payload,
      });
    } else {
      // SELF, SINGLE, AREA — pass the single target persona (or null for self/area/no-target).
      performCast.mutate({
        technique_id: selectedTechnique.id,
        target_persona: castTargetPersonaId ?? null,
        ...payload,
      });
    }
  }

  function handleCastTargetConfirm(ids: number[]) {
    const cardinality =
      selectedTechnique?.target_spec?.cardinality ?? selectedTechnique?.target_type;
    if (cardinality === 'filtered_group') {
      setCastTargetPersonaIds(ids);
    } else {
      setCastTargetPersonaId(ids[0] ?? null);
    }
    setCastPickingTarget(false);
  }

  function handleCastTargetCancel() {
    setCastPickingTarget(false);
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
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          // A dismissed ledger is stale on the next open — drop it.
          if (!next) setCastLedgerResult(null);
        }}
      >
        <PopoverTrigger asChild>
          <Button size="icon" className="h-12 w-12 rounded-full shadow-lg">
            <Swords className="h-5 w-5" />
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" align="end" className="w-80">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold">Actions</h3>

            {/* Effort level picker — controls how hard the initiator pushes (#1275) */}
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-xs text-muted-foreground">Effort:</span>
              <Select value={effortLevel} onValueChange={setEffortLevel}>
                <SelectTrigger className="h-7 text-xs" aria-label="Effort level">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EFFORT_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

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

            {/* ----------------------------------------------------------------
                Standalone Cast section
            ---------------------------------------------------------------- */}
            <div className="border-t border-muted pt-3">
              <button
                type="button"
                className="flex w-full items-center justify-between text-sm font-semibold"
                onClick={() => {
                  setCastOpen((prev) => !prev);
                  if (castOpen) {
                    setSelectedTechnique(null);
                    setCastTargetPersonaId(null);
                    setCastTargetPersonaIds([]);
                    setCastPickingTarget(false);
                    setCastLedgerResult(null);
                    performCast.reset();
                    pull.reset();
                  } else {
                    setCastLedgerResult(null);
                  }
                }}
                aria-expanded={castOpen}
                aria-controls="cast-section"
              >
                <span className="flex items-center gap-1">
                  <Wand2 className="h-3.5 w-3.5" />
                  Cast
                </span>
                {castOpen ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>

              {castOpen && (
                <div id="cast-section" className="mt-2 space-y-2">
                  {castLedgerResult?.result?.power_ledger && (
                    <div className="space-y-2" data-testid="cast-ledger-result">
                      <PowerLedgerPanel ledger={castLedgerResult.result.power_ledger} />
                      <Button
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setCastLedgerResult(null);
                          setOpen(false);
                          setCastOpen(false);
                        }}
                      >
                        Done
                      </Button>
                    </div>
                  )}

                  {!castLedgerResult && isCastLoading && (
                    <p className="text-xs text-muted-foreground">Loading techniques...</p>
                  )}

                  {!castLedgerResult && !isCastLoading && castableTechniques.length === 0 && (
                    <p className="text-xs text-muted-foreground">No castable techniques.</p>
                  )}

                  {!castLedgerResult && !isCastLoading && castableTechniques.length > 0 && (
                    <div className="space-y-1">
                      {castableTechniques.map((tech) => {
                        const isSelected = selectedTechnique?.id === tech.id;
                        return (
                          <button
                            key={tech.id}
                            type="button"
                            onClick={() => handleTechniqueSelect(tech)}
                            className={`flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-muted/50 ${
                              isSelected ? 'bg-muted font-semibold ring-1 ring-primary/40' : ''
                            }`}
                          >
                            <span className="flex items-center gap-1">
                              {tech.hostile && (
                                <AlertTriangle
                                  aria-label="Hostile — may trigger combat"
                                  className="h-3 w-3 shrink-0 text-amber-400"
                                />
                              )}
                              {tech.name}
                            </span>
                            <span className="ml-2 shrink-0 text-muted-foreground">
                              {tech.anima_cost} anima
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {!castLedgerResult && selectedTechnique && (
                    <div className="space-y-2 rounded border border-muted p-2">
                      <p className="text-xs font-medium">{selectedTechnique.name}</p>

                      {selectedTechnique.hostile && (
                        <p className="flex items-center gap-1 text-xs text-amber-500">
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          Hostile — casting at another character may start combat.
                        </p>
                      )}

                      {/* Target selector — driven by target_spec.cardinality (#1321) */}
                      {(() => {
                        const cardinality =
                          selectedTechnique.target_spec?.cardinality ??
                          selectedTechnique.target_type;
                        if (cardinality === 'self') {
                          // SELF: no picker — cast resolves on the caster.
                          return (
                            <p className="text-xs text-muted-foreground">Targets: self (auto)</p>
                          );
                        }
                        if (cardinality === 'area') {
                          // AREA: backend auto-expands; no picker needed.
                          return (
                            <p className="text-xs text-muted-foreground">
                              Targets: all eligible in scene (area cast)
                            </p>
                          );
                        }
                        if (cardinality === 'filtered_group') {
                          // FILTERED_GROUP: multi-select via TargetPicker.
                          const chosenNames = castTargetPersonaIds
                            .map((id) => candidates.find((c) => c.id === id)?.name)
                            .filter(Boolean)
                            .join(', ');
                          return (
                            <div className="flex items-center gap-1">
                              <span className="text-xs text-muted-foreground">Targets:</span>
                              <button
                                type="button"
                                onClick={() => setCastPickingTarget(true)}
                                className={`rounded px-2 py-0.5 text-xs ${
                                  castTargetPersonaIds.length > 0 || castPickingTarget
                                    ? 'bg-primary text-primary-foreground'
                                    : 'hover:bg-muted/50'
                                }`}
                              >
                                {castTargetPersonaIds.length > 0 ? chosenNames : 'Choose targets…'}
                              </button>
                            </div>
                          );
                        }
                        // Default: SINGLE — original Self/Room + single persona picker.
                        return (
                          <div className="flex items-center gap-1">
                            <span className="text-xs text-muted-foreground">Target:</span>
                            <button
                              type="button"
                              onClick={() => {
                                setCastTargetPersonaId(null);
                              }}
                              className={`rounded px-2 py-0.5 text-xs ${
                                castTargetPersonaId === null && !castPickingTarget
                                  ? 'bg-primary text-primary-foreground'
                                  : 'hover:bg-muted/50'
                              }`}
                            >
                              Self / Room
                            </button>
                            <button
                              type="button"
                              onClick={() => setCastPickingTarget(true)}
                              className={`rounded px-2 py-0.5 text-xs ${
                                castTargetPersonaId !== null || castPickingTarget
                                  ? 'bg-primary text-primary-foreground'
                                  : 'hover:bg-muted/50'
                              }`}
                            >
                              {castTargetPersonaId !== null
                                ? (candidates.find((c) => c.id === castTargetPersonaId)?.name ??
                                  'Persona')
                                : 'Choose persona…'}
                            </button>
                          </div>
                        );
                      })()}

                      {/* Thread pulls — optional resonance surge on this cast */}
                      {pull.pullsContext && characterId !== null && (
                        <div className="border-t border-border/50 pt-2">
                          <ThreadPullPicker
                            characterSheetId={characterId}
                            actionContext={pull.pullsContext}
                            selectedPulls={pull.selectedPulls}
                            onPullsChange={pull.handlePullsChange}
                            showInapplicable={pull.showInapplicable}
                            onToggleInapplicable={pull.setShowInapplicable}
                            onAutoRevertNotice={pull.setPullNotice}
                            balanceByResonanceId={pull.balanceByResonanceId}
                          />
                          {pull.pullNotice && (
                            <p className="mt-1 text-xs text-amber-400">{pull.pullNotice}</p>
                          )}
                        </div>
                      )}

                      <Button
                        size="sm"
                        className="w-full"
                        disabled={
                          performCast.isPending ||
                          initiatorPersonaId === null ||
                          ((selectedTechnique.target_spec?.cardinality ??
                            selectedTechnique.target_type) === 'filtered_group' &&
                            castTargetPersonaIds.length === 0)
                        }
                        onClick={handleCastCommit}
                      >
                        {performCast.isPending ? 'Casting…' : `Cast ${selectedTechnique.name}`}
                      </Button>
                      {performCast.isError && (
                        <p className="mt-1 text-xs text-destructive" role="alert">
                          {extractErrorMessage(performCast.error)}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
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

      {boonAskState && (
        <BoonAskForm
          targetPersonaId={boonAskState.targetId}
          targetName={candidates.find((c) => c.id === boonAskState.targetId)?.name}
          onConfirm={handleBoonConfirm}
          onCancel={() => setBoonAskState(null)}
        />
      )}

      {castPickingTarget && selectedTechnique && (
        <TargetPicker
          spec={
            selectedTechnique.target_spec ?? {
              kind: 'persona',
              cardinality: 'single',
              filters: {
                in_same_scene: true,
                exclude_self: false,
                must_be_conscious: false,
              },
            }
          }
          candidates={candidates}
          onConfirm={handleCastTargetConfirm}
          onCancel={handleCastTargetCancel}
        />
      )}
    </div>
  );
}
