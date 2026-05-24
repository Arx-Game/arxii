import { useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { createActionRequest } from '../actionQueries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneInteractionPanel } from '../components/SceneInteractionPanel';
import { ActionPanel } from '../components/ActionPanel';
import { PlaceBar } from '../components/PlaceBar';
import { ConsentPrompt } from '../components/ConsentPrompt';
import { SineatingInbox } from '@/magic/components/SineatingInbox';
import { SoulTetherRescuePrompt } from '@/magic/components/SoulTetherRescuePrompt';
import { CommandInput } from '@/game/components/CommandInput';
import type { ComposerMode } from '@/game/components/CommandInput';
import type { ActionAttachmentInfo } from '../actionTypes';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { PendingActionAttachments } from '../components/PendingActionAttachments';
import { usePendingUnlinkedActions } from '../hooks/usePendingUnlinkedActions';

export function SceneDetailPage() {
  const { id = '' } = useParams();
  const { data: scene, refetch } = useQuery<SceneDetail>({
    queryKey: ['scene', id],
    queryFn: () => fetchScene(id),
    refetchInterval: (query) => (query.state.data?.is_active ? 60000 : false),
  });

  const isActive = scene?.is_active ?? false;
  const roomName = scene?.name ?? 'Room';
  const activeCharacter = useAppSelector((state) => state.game.active);

  // Resolve the active character's primary persona id for submit_pose REST calls.
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const personaId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter)?.primary_persona_id ?? null,
    [myRosterEntries, activeCharacter]
  );

  // Track IDs the user has detached from the auto-attach chip strip.
  const [detachedActionIds, setDetachedActionIds] = useState<number[]>([]);

  const handleDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => (prev.includes(actionId) ? prev : [...prev, actionId]));
  }, []);

  const handleUndoDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => prev.filter((id) => id !== actionId));
  }, []);

  const handlePoseSubmitted = useCallback(() => {
    setDetachedActionIds([]);
  }, []);

  // Pending unlinked actions for the chip strip.
  const { data: pendingActions } = usePendingUnlinkedActions(id, personaId);
  const pendingActionIds = useMemo(() => pendingActions.map((a) => a.id), [pendingActions]);

  const [composerMode, setComposerMode] = useState<ComposerMode>({
    command: 'pose',
    targets: [],
    label: `Pose \u2192 Room`,
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
    onError: () => {
      // Keep the attachment so user can retry
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

  // Update the default label when scene name loads
  const handleComposerModeChange = useCallback((mode: ComposerMode) => {
    setComposerMode(mode);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-4 pt-4">
        <SceneHeader scene={scene} onRefresh={() => refetch()} />
        {isActive && <ConsentPrompt sceneId={id} />}
        {isActive && <SineatingInbox />}
        {isActive && <SoulTetherRescuePrompt />}
        <PlaceBar sceneId={id} />
      </div>

      {/* Main interaction area with threading */}
      <SceneInteractionPanel
        sceneId={id}
        roomName={roomName}
        onComposerModeChange={handleComposerModeChange}
        onAddTarget={setPendingTarget}
        onAttachAction={handleActionAttach}
      />

      {/* Composer + Action Panel */}
      {isActive && (
        <div className="shrink-0">
          {activeCharacter && (
            <>
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
            </>
          )}
          <ActionPanel sceneId={id} />
        </div>
      )}
    </div>
  );
}
