import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swords, Zap, AlertTriangle, ChevronDown, ChevronUp, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import {
  fetchAvailableActions,
  createActionRequest,
  castTechnique,
  useCastableTechniques,
} from '../actionQueries';
import { fetchScene, sceneKeys } from '../queries';
import { PowerLedgerPanel } from '@/magic/components/PowerLedgerPanel';
import { ThreadPullPicker } from '@/magic/components/threads/ThreadPullPicker';
import { useThreads } from '@/magic/queries';
import type { ApplicablePullsRequest, Thread } from '@/magic/types';
import type {
  PlayerAction,
  AvailableEnhancement,
  CastableTechnique,
  CastPullRequestBody,
  CastResponse,
} from '../actionTypes';
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

  // Cast section state
  const [castOpen, setCastOpen] = useState(false);
  const [selectedTechnique, setSelectedTechnique] = useState<CastableTechnique | null>(null);
  const [castTargetPersonaId, setCastTargetPersonaId] = useState<number | null>(null);
  const [castPickingTarget, setCastPickingTarget] = useState(false);
  const [castLedgerResult, setCastLedgerResult] = useState<CastResponse | null>(null);
  // Thread-pull state for the cast flow (#854) — thread id → committed tier.
  const [selectedPulls, setSelectedPulls] = useState<Record<number, 0 | 1 | 2 | 3>>({});
  const [showInapplicablePulls, setShowInapplicablePulls] = useState(false);
  const [pullNotice, setPullNotice] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk and primary persona.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName) ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const characterId = activeEntry?.character_id ?? null;
  const initiatorPersonaId = activeEntry?.primary_persona_id ?? null;

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

  // Castable techniques for the standalone cast flow.
  const { data: castableTechniques = [], isLoading: isCastLoading } = useCastableTechniques(
    open ? initiatorPersonaId : null
  );

  // Threads — used to map a pulled thread id back to its resonance for the
  // cast payload and to enforce the single-(resonance, tier)-group constraint.
  const { data: threadsData } = useThreads();
  const threadById = useMemo(() => {
    const map = new Map<number, Thread>();
    for (const thread of threadsData?.results ?? []) {
      map.set(thread.id, thread);
    }
    return map;
  }, [threadsData]);

  // Applicability context for the thread-pull picker — only while a technique
  // is selected in the open cast section.
  const pullsContext = useMemo<ApplicablePullsRequest | null>(() => {
    if (!castOpen || !selectedTechnique || characterId === null) return null;
    return {
      character_sheet_id: characterId,
      technique_id: selectedTechnique.id,
      target_persona_id: castTargetPersonaId,
      scene_id: Number(sceneId),
    };
  }, [castOpen, selectedTechnique, characterId, castTargetPersonaId, sceneId]);

  const performCast = useMutation({
    mutationFn: (params: {
      technique_id: number;
      target_persona?: number | null;
      strain_commitment?: number;
      pull?: CastPullRequestBody;
    }) =>
      castTechnique(sceneId, {
        initiator_persona: initiatorPersonaId!,
        ...params,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      setSelectedTechnique(null);
      setCastTargetPersonaId(null);
      setCastPickingTarget(false);
      setSelectedPulls({});
      setPullNotice(null);
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
  // Cast flow handlers
  // ------------------------------------------------------------------------

  function handleTechniqueSelect(technique: CastableTechnique) {
    setSelectedTechnique(technique);
    setCastTargetPersonaId(null);
    setCastLedgerResult(null);
    setSelectedPulls({});
    setPullNotice(null);
  }

  /**
   * Constrain pull selection to a single (resonance, tier) group — the cast
   * payload's pull declaration is singular, so any newly raised pull reverts
   * every other paid pull that disagrees on resonance or tier.
   */
  function handlePullsChange(next: Record<number, 0 | 1 | 2 | 3>) {
    const changed = Object.entries(next).find(
      ([id, tier]) => (selectedPulls[Number(id)] ?? 0) !== tier && tier > 0
    );
    if (changed) {
      const changedId = Number(changed[0]);
      const changedTier = changed[1];
      const changedResonance = threadById.get(changedId)?.resonance;
      let reverted = 0;
      const constrained = { ...next };
      for (const [idStr, tier] of Object.entries(next)) {
        const id = Number(idStr);
        if (id === changedId || tier === 0) continue;
        if (tier !== changedTier || threadById.get(id)?.resonance !== changedResonance) {
          constrained[id] = 0;
          reverted++;
        }
      }
      setPullNotice(reverted > 0 ? 'Pulls in one cast share a single resonance and tier.' : null);
      setSelectedPulls(constrained);
      return;
    }
    // Deselects pass through; a conflict notice is stale once no paid pull remains.
    if (!Object.values(next).some((tier) => tier > 0)) {
      setPullNotice(null);
    }
    setSelectedPulls(next);
  }

  function handleCastCommit() {
    if (!selectedTechnique || initiatorPersonaId === null) return;
    const paid = Object.entries(selectedPulls).filter(([, tier]) => tier > 0);
    let pull: CastPullRequestBody | undefined;
    if (paid.length > 0) {
      const firstThread = threadById.get(Number(paid[0][0]));
      if (firstThread) {
        pull = {
          resonance_id: firstThread.resonance,
          tier: paid[0][1] as 1 | 2 | 3,
          thread_ids: paid.map(([id]) => Number(id)),
        };
      }
    }
    performCast.mutate({
      technique_id: selectedTechnique.id,
      target_persona: castTargetPersonaId ?? null,
      ...(pull ? { pull } : {}),
    });
  }

  function handleCastTargetConfirm(ids: number[]) {
    setCastTargetPersonaId(ids[0] ?? null);
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
                    setCastPickingTarget(false);
                    setCastLedgerResult(null);
                    setSelectedPulls({});
                    setPullNotice(null);
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

                      {/* Target selector */}
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

                      {/* Thread pulls — optional resonance surge on this cast */}
                      {pullsContext && characterId !== null && (
                        <div className="border-t border-border/50 pt-2">
                          <ThreadPullPicker
                            characterSheetId={characterId}
                            actionContext={pullsContext}
                            selectedPulls={selectedPulls}
                            onPullsChange={handlePullsChange}
                            showInapplicable={showInapplicablePulls}
                            onToggleInapplicable={setShowInapplicablePulls}
                            onAutoRevertNotice={setPullNotice}
                          />
                          {pullNotice && (
                            <p className="mt-1 text-xs text-amber-400">{pullNotice}</p>
                          )}
                        </div>
                      )}

                      <Button
                        size="sm"
                        className="w-full"
                        disabled={performCast.isPending || initiatorPersonaId === null}
                        onClick={handleCastCommit}
                      >
                        {performCast.isPending ? 'Casting…' : `Cast ${selectedTechnique.name}`}
                      </Button>
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

      {castPickingTarget && selectedTechnique && (
        <TargetPicker
          spec={{
            kind: 'persona',
            cardinality: 'single',
            filters: {
              in_same_scene: true,
              in_same_zone: false,
              exclude_self: false,
              must_be_conscious: false,
            },
          }}
          candidates={candidates}
          onConfirm={handleCastTargetConfirm}
          onCancel={handleCastTargetCancel}
        />
      )}
    </div>
  );
}
