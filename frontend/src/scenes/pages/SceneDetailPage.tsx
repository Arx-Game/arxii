import { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { createActionRequest } from '../actionQueries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneInteractionPanel } from '../components/SceneInteractionPanel';
import { ActionPanel } from '../components/ActionPanel';
import { PlaceBar } from '../components/PlaceBar';
import { ConsentPrompt } from '../components/ConsentPrompt';
import { CommandInput } from '@/game/components/CommandInput';
import type { ComposerMode } from '@/game/components/CommandInput';
import type { ActionAttachmentInfo } from '../actionTypes';
import { useAppSelector } from '@/store/hooks';

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
      queryClient.invalidateQueries({ queryKey: ['scene-messages', id] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', id] });
    },
  });

  const handleSubmitAction = useCallback(
    (action: ActionAttachmentInfo) => {
      submitAction.mutate(action);
      setActionAttachment(null);
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
            <CommandInput
              character={activeCharacter}
              composerMode={composerMode}
              targetToAppend={targetToAppend}
              onTargetConsumed={handleTargetConsumed}
              sceneId={id}
              actionAttachment={actionAttachment}
              onActionAttach={handleActionAttach}
              onActionDetach={handleActionDetach}
              onSubmitAction={handleSubmitAction}
            />
          )}
          <ActionPanel sceneId={id} />
        </div>
      )}
    </div>
  );
}
