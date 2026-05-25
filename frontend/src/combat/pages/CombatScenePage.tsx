/**
 * CombatScenePage — the unified C-frame combat UI.
 *
 * Route: /scenes/:id/combat
 *
 * Layout:
 *   [ SceneHeader (full width)                             ]
 *   [ SceneInteractionPanel (pose log)  ] [ CombatTurnPanel ]
 *   [ PendingActionAttachments          ] [   YourTurn       ]
 *   [ CommandInput (composer)           ] [   Rail sections  ]
 *
 * The scene's active encounter is resolved via useEncounterForScene.
 * The viewer's characterId/characterSheetId are resolved from the
 * active roster entry — MyRosterEntry.character_id doubles as the
 * character_sheet pk (CharacterSheet uses primary_key=True on its
 * OneToOne to ObjectDB).
 *
 * Phase 11 of the unified-combat-ui plan.
 * See: docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §2
 */

import { useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/queries';
import { createActionRequest } from '@/scenes/actionQueries';
import { SceneHeader } from '@/scenes/components/SceneHeader';
import { SceneInteractionPanel } from '@/scenes/components/SceneInteractionPanel';
import { PendingActionAttachments } from '@/scenes/components/PendingActionAttachments';
import { CommandInput } from '@/game/components/CommandInput';
import type { ComposerMode } from '@/game/components/CommandInput';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { usePendingUnlinkedActions } from '@/scenes/hooks/usePendingUnlinkedActions';
import { useEncounterForScene } from '@/combat/queries';
import { CombatTurnPanel } from '@/combat/CombatTurnPanel';

// ---------------------------------------------------------------------------
// CombatScenePage
// ---------------------------------------------------------------------------

export function CombatScenePage() {
  const { id = '' } = useParams();
  const sceneIdNum = Number(id);

  // Scene data — sceneKeys.detail(id) produces ['scene', id] to match the
  // legacy shape in SceneDetailPage, so both pages share the same cache entry.
  const { data: scene, refetch } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(id),
    queryFn: () => fetchScene(id),
    refetchInterval: (query) => (query.state.data?.is_active ? 60000 : false),
  });

  const isActive = scene?.is_active ?? false;

  // Active encounter for this scene
  const { data: encounterListItem, isLoading: encounterLoading } = useEncounterForScene(sceneIdNum);

  // Active character from Redux global state
  const activeCharacter = useAppSelector((state) => state.game.active);

  // Resolve the active character's character_id (== character_sheet_id) and persona_id.
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const characterId = activeEntry?.character_id ?? 0;
  const characterSheetId = activeEntry?.character_id ?? 0; // same pk — see MyRosterEntry type
  const personaId = activeEntry?.primary_persona_id ?? null;

  // Detached action IDs for the chip strip
  const [detachedActionIds, setDetachedActionIds] = useState<number[]>([]);

  const handleDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => (prev.includes(actionId) ? prev : [...prev, actionId]));
  }, []);

  const handleUndoDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => prev.filter((prevId) => prevId !== actionId));
  }, []);

  const handlePoseSubmitted = useCallback(() => {
    setDetachedActionIds([]);
  }, []);

  // Pending unlinked actions for the chip strip
  const { data: pendingActions } = usePendingUnlinkedActions(id, personaId);
  const pendingActionIds = useMemo(() => pendingActions.map((a) => a.id), [pendingActions]);

  // Composer mode state
  const [composerMode, setComposerMode] = useState<ComposerMode>({
    command: 'pose',
    targets: [],
    label: `Pose → Room`,
  });

  const [targetToAppend, setPendingTarget] = useState<string | null>(null);
  const [actionAttachment, setActionAttachment] = useState<ActionAttachmentInfo | null>(null);
  const queryClient = useQueryClient();

  const submitAction = useMutation({
    mutationFn: (action: ActionAttachmentInfo) =>
      createActionRequest(id, {
        action_key: action.actionKey,
        target_persona_id: action.targetPersonaId,
        technique_id: action.techniqueId,
      }),
    onSuccess: () => {
      setActionAttachment(null);
      queryClient.invalidateQueries({ queryKey: ['scene-messages', id] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', id] });
    },
  });

  const handleSubmitAction = useCallback(
    (action: ActionAttachmentInfo) => {
      submitAction.mutate(action);
    },
    [submitAction]
  );

  const handleTargetConsumed = useCallback(() => {
    setPendingTarget(null);
  }, []);

  const handleActionAttach = useCallback((action: ActionAttachmentInfo) => {
    setActionAttachment(action);
  }, []);

  const handleActionDetach = useCallback(() => {
    setActionAttachment(null);
  }, []);

  const handleComposerModeChange = useCallback((mode: ComposerMode) => {
    setComposerMode(mode);
  }, []);

  // ---------------------------------------------------------------------------
  // No-active-encounter empty state
  // ---------------------------------------------------------------------------

  // While loading encounters, show nothing extra — the layout still renders.
  // After load: if there is no active encounter, surface the empty state inside
  // the right column instead of CombatTurnPanel.
  const hasActiveEncounter = !encounterLoading && encounterListItem != null;
  const encounterId = encounterListItem?.id ?? 0;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const roomName = scene?.name ?? 'Room';

  return (
    <div className="flex h-full flex-col" data-testid="combat-scene-page">
      {/* Full-width header */}
      <div className="shrink-0 px-4 pt-4" data-testid="combat-scene-header">
        <SceneHeader scene={scene} onRefresh={() => refetch()} />
      </div>

      {/* C-frame grid: left (pose log + composer) | right (CombatTurnPanel) */}
      <div
        className={cn('grid min-h-0 flex-1 grid-cols-[1fr_360px] gap-4 px-4 pb-4')}
        data-testid="combat-scene-grid"
      >
        {/* Left column: pose log + composer */}
        <div className="flex min-h-0 flex-col" data-testid="combat-scene-left">
          {/* Scrollable pose log */}
          <SceneInteractionPanel
            sceneId={id}
            roomName={roomName}
            onComposerModeChange={handleComposerModeChange}
            onAddTarget={setPendingTarget}
            onAttachAction={handleActionAttach}
          />

          {/* Composer (only when scene is active and character is resolved) */}
          {isActive && activeCharacter && (
            <div className="shrink-0" data-testid="combat-scene-composer">
              <PendingActionAttachments
                sceneId={id}
                personaId={personaId}
                detachedIds={detachedActionIds}
                onDetach={handleDetach}
                onUndoDetach={handleUndoDetach}
              />
              <CommandInput
                character={activeCharacter}
                composerMode={composerMode}
                onModeChange={handleComposerModeChange}
                targetToAppend={targetToAppend}
                onTargetConsumed={handleTargetConsumed}
                sceneId={id}
                actionAttachment={actionAttachment}
                onActionAttach={handleActionAttach}
                onActionDetach={handleActionDetach}
                onSubmitAction={handleSubmitAction}
                personaId={personaId}
                pendingActionIds={pendingActionIds}
                detachedActionIds={detachedActionIds}
                onPoseSubmitted={handlePoseSubmitted}
              />
            </div>
          )}
        </div>

        {/* Right column: CombatTurnPanel */}
        <div className="min-h-0 overflow-y-auto" data-testid="combat-scene-right">
          {encounterLoading ? (
            <div
              className="p-4 text-sm text-muted-foreground"
              data-testid="combat-encounter-loading"
            >
              Loading combat state…
            </div>
          ) : hasActiveEncounter ? (
            <CombatTurnPanel
              encounterId={encounterId}
              characterId={characterId}
              characterSheetId={characterSheetId}
            />
          ) : (
            <div
              className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground"
              data-testid="combat-no-encounter"
            >
              No active combat in this scene.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
