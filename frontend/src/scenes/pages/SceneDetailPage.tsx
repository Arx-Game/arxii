import { useState, useCallback, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { createActionRequest, fetchPlaces } from '../actionQueries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneInteractionPanel } from '../components/SceneInteractionPanel';
import { ActionPanel } from '../components/ActionPanel';
import { PlaceBar } from '../components/PlaceBar';
import { SceneTacticalMap } from '../components/SceneTacticalMap';
import { HighlightReel } from '../components/HighlightReel';
import { ConsentPrompt } from '../components/ConsentPrompt';
import { SceneLinesAndVeilsCard } from '@/boundaries/components/SceneLinesAndVeilsCard';
import { SineatingInbox } from '@/magic/components/SineatingInbox';
import { SoulTetherRescuePrompt } from '@/magic/components/SoulTetherRescuePrompt';
import { EntryFlourishOfferGate } from '@/magic/components/EntryFlourishOfferGate';
import { CommandInput } from '@/game/components/CommandInput';
import type { ComposerMode } from '@/game/components/CommandInput';
import { CharacterCardDrawer } from '@/game/components/CharacterCardDrawer';
import type { PoseUnitAvatarClickPersona } from '../components/PoseUnit';
import type { ActionAttachmentInfo } from '../actionTypes';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { PendingActionAttachments } from '../components/PendingActionAttachments';
import { usePendingUnlinkedActions } from '../hooks/usePendingUnlinkedActions';
import { useBattleForSceneQuery } from '@/battles/queries';
import { RitualProposedChip } from '@/rituals/components/RitualProposedChip';

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
  const { data: battle } = useBattleForSceneQuery(id ? Number(id) : null);

  // Resolve the active character's primary persona id for submit_pose REST calls.
  // Also derives characterSheetId: CharacterSheet uses OneToOneField(primary_key=True)
  // to ObjectDB, so character_id === character_sheet pk.
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const personaId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter)?.primary_persona_id ?? null,
    [myRosterEntries, activeCharacter]
  );
  const characterSheetId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter)?.character_id ?? 0,
    [myRosterEntries, activeCharacter]
  );
  // The active character's own RosterEntry id (#2156 Task 7) — the FriendButton's
  // `viewerEntryId` inside the character-card drawer.
  const viewerEntryId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter)?.id ?? null,
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

  // Character-card drawer (#2156 Task 7): the clicked bubble's persona identity,
  // or null when the drawer is closed. Mirrors GamePage's state — the drawer
  // opens "in place" over this record page's feed, not as a route navigation.
  const [cardPersona, setCardPersona] = useState<PoseUnitAvatarClickPersona | null>(null);
  const handleWhisper = useCallback(
    (name: string) => {
      handleComposerModeChange({ command: 'whisper', targets: [name], label: `Whisper → ${name}` });
      setCardPersona(null);
    },
    [handleComposerModeChange]
  );

  // `isAtPlace` (#2156, Task 6): derived from the SAME `['scene-places',
  // placesRoomId]` query key `PlaceBar` uses below, so React Query dedupes the
  // two fetches into one (query-reuse, matching GamePage's approach).
  // `fetchPlaces` filters `?room=<id>` — a ROOM id, not the scene id — so this
  // derives the room id from `scene.location.id` (fold-in fix, #2156: the
  // earlier version passed the *scene* id here and to `PlaceBar`, which only
  // worked by coincidence when scene pk === room pk).
  const placesRoomId = scene?.location?.id != null ? String(scene.location.id) : undefined;
  const { data: placesData } = useQuery({
    queryKey: ['scene-places', placesRoomId],
    queryFn: () => fetchPlaces(placesRoomId!),
    enabled: !!placesRoomId,
  });
  const isAtPlace = placesData?.results?.some((place) => place.viewer_is_present) ?? false;

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-4 pt-4">
        <SceneHeader scene={scene} onRefresh={() => refetch()} />
        {battle && battle.outcome === 'unresolved' && (
          <Link
            to={`/scenes/${id}/battle`}
            className="mt-1 inline-block text-sm text-blue-600 hover:underline"
            data-testid="scene-battle-map-link"
          >
            Battle Map
          </Link>
        )}
        {battle && battle.outcome !== 'unresolved' && (
          <Link
            to={`/battles/${battle.id}`}
            className="mt-1 inline-block text-sm text-blue-600 hover:underline"
            data-testid="scene-battle-writeup-link"
          >
            Battle Writeup
          </Link>
        )}
        {scene && <RitualProposedChip sceneId={scene.id} />}
        {isActive && <ConsentPrompt sceneId={id} />}
        {isActive && <SineatingInbox />}
        {isActive && <SoulTetherRescuePrompt />}
        {isActive && <EntryFlourishOfferGate characterSheetId={characterSheetId} />}
        {scene && <SceneLinesAndVeilsCard sceneId={id} />}
        {placesRoomId && <PlaceBar sceneId={placesRoomId} />}
        <SceneTacticalMap sceneId={id} />
        <HighlightReel sceneId={id} canGm={scene?.viewer_can_gm} />
      </div>

      {/* Main interaction area with threading */}
      <SceneInteractionPanel
        sceneId={id}
        roomName={roomName}
        onComposerModeChange={handleComposerModeChange}
        onAddTarget={setPendingTarget}
        onAttachAction={handleActionAttach}
        canGm={scene?.viewer_can_gm}
        onAvatarClick={setCardPersona}
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
                isAtPlace={isAtPlace}
              />
            </>
          )}
          <ActionPanel sceneId={id} />
        </div>
      )}
      <CharacterCardDrawer
        persona={cardPersona}
        onClose={() => setCardPersona(null)}
        viewerEntryId={viewerEntryId}
        onWhisper={handleWhisper}
      />
    </div>
  );
}
