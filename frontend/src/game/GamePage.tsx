import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { GameLayout } from './components/GameLayout';
import { GameTopBar } from './components/GameTopBar';
import { GameWindow } from './components/GameWindow';
import { CharacterCardDrawer } from './components/CharacterCardDrawer';
import { ConversationSidebar } from './components/ConversationSidebar';
import { FocusPanel } from './components/FocusPanel';
import { SidebarTabPanel } from './components/SidebarTabPanel';
import { PresencePanel } from './components/PresencePanel';
import { EventsSidebarPanel } from '@/events/components/EventsSidebarPanel';
import { useEncounterForScene } from '@/combat/queries';
import { useBattleForSceneQuery } from '@/battles/queries';
import { StoryTray } from '@/missions/components/StoryTray';
import { JournalTab } from '@/journals/components/JournalTab';
import { StatusPanel } from '@/status/components/StatusPanel';
import { InventorySidebarPanel } from '@/inventory/components/InventorySidebarPanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useFocusStack, type FocusEntry } from '@/inventory/hooks/useFocusStack';
import { Link } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { markThreadSeen, setSceneBaseline } from '@/store/gameSlice';
import { useSceneInteractions } from '@/scenes/hooks/useSceneInteractions';
import { useThreading, getThreadKey } from '@/scenes/hooks/useThreading';
import { threadToComposerMode } from '@/scenes/hooks/threadToComposerMode';
import { usePendingUnlinkedActions } from '@/scenes/hooks/usePendingUnlinkedActions';
import { ConsentPrompt } from '@/scenes/components/ConsentPrompt';
import { PlaceBar } from '@/scenes/components/PlaceBar';
import { ActionPanel } from '@/scenes/components/ActionPanel';
import { PendingActionAttachments } from '@/scenes/components/PendingActionAttachments';
import { createActionRequest, fetchPlaces } from '@/scenes/actionQueries';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { ComposerMode } from './components/CommandInput';

const DEFAULT_ROOM_ENTRY: FocusEntry = {
  kind: 'room',
  room: null,
  sceneSummary: null,
};

// Stable empty-object reference so `useThreading`'s memo doesn't see a "changed"
// lastSeenByThread on every render when there's no active session yet (#2156).
const EMPTY_THREAD_LAST_SEEN: Record<string, number> = {};

export function GamePage() {
  const account = useAccount();
  const dispatch = useAppDispatch();
  const { data: characters = [] } = useMyRosterEntriesQuery();
  const { sessions, active } = useAppSelector((state) => state.game);

  const focus = useFocusStack(DEFAULT_ROOM_ENTRY);

  // Resolve the active character name to its underlying ObjectDB pk (copied
  // from WardrobePage's snippet — CharacterSheet is OneToOne with ObjectDB
  // via primary_key=True, so the same id doubles as the character sheet pk).
  const activeEntry = useMemo(
    () => characters.find((entry) => entry.name === active) ?? null,
    [characters, active]
  );
  const activeCharacterId = activeEntry?.character_id ?? null;
  // Lifted from GameWindow (#2156 review fold-in) — dedupes the roster query
  // that both GamePage and GameWindow used to call independently.
  const personaId = activeEntry?.primary_persona_id ?? null;
  // The active character's own RosterEntry id (#2156 Task 7) — the FriendButton's
  // `viewerEntryId` inside the character-card drawer.
  const viewerEntryId = activeEntry?.id ?? null;

  const activeSession = active ? sessions[active] : null;
  const roomData = activeSession?.room ?? null;
  const sceneData = activeSession?.scene ?? null;
  const sceneId = sceneData ? String(sceneData.id) : undefined;
  const roomName = sceneData?.name ?? roomData?.name ?? 'Room';

  // RoomHeader combat/battle badges (#2157) — GamePage is the composition root,
  // so it calls both hooks once here and threads the derived booleans down
  // through FocusPanel -> RoomPanel -> RoomHeader.
  const { data: activeEncounter } = useEncounterForScene(sceneData?.id ?? 0);
  const { data: activeBattle } = useBattleForSceneQuery(sceneData?.id ?? null);
  const hasActiveEncounter = activeEncounter != null;
  const hasActiveBattle = activeBattle != null && activeBattle.outcome === 'unresolved';

  // GamePage is the composition root (#2156): it calls the scene-feed +
  // threading hooks once for the active session's scene and feeds both the
  // left column (ThreadSidebar via ConversationSidebar) and the center
  // (SceneMessages + composer). Called unconditionally — sceneId is simply
  // undefined with no active scene, which both hooks handle without firing
  // network calls or producing threads.
  const { allInteractions, hasNextPage, fetchNextPage } = useSceneInteractions(sceneId);
  const threadLastSeen = activeSession?.threadLastSeen ?? EMPTY_THREAD_LAST_SEEN;
  const sceneBaselineId = activeSession?.sceneBaselineId ?? null;
  const threading = useThreading(allInteractions, roomName, {
    lastSeenByThread: threadLastSeen,
    viewerPersonaId: personaId,
    sceneBaselineId,
  });
  const [composerMode, setComposerMode] = useState<ComposerMode | undefined>();

  // Character-card drawer (#2156 Task 7): the clicked bubble's persona identity,
  // or null when the drawer is closed. GamePage owns this state (mirrored on
  // SceneDetailPage) since the drawer opens "in place" over whichever surface
  // the avatar was clicked on, not as a route navigation.
  const [cardPersona, setCardPersona] = useState<PoseUnitAvatarClickPersona | null>(null);
  const handleWhisper = useCallback((name: string) => {
    setComposerMode({ command: 'whisper', targets: [name], label: `Whisper → ${name}` });
    setCardPersona(null);
  }, []);

  // Scene-load baseline (#2156 review fix): a single scalar snapshot, not a
  // per-thread-key one. The old per-key baseline one-shotted per KEY, so a
  // brand-new thread appearing mid-session (e.g. a first whisper) got its own
  // key baselined to its first message's id the moment it was observed —
  // countUnread's strict `>` then suppressed the badge on that very first
  // message. Instead: the first time this effect runs for a given puppet+scene,
  // capture the highest interaction id present at that moment as
  // `sceneBaselineId` and never touch it again for this scene.
  // `useThreading`'s `countUnread` falls back to this scalar only for thread
  // keys with no `threadLastSeen` entry, so pre-existing threads (which get a
  // `threadLastSeen` entry from the selected-thread effect below, or already
  // had one) stay zeroed while a genuinely new thread badges from message one.
  // `maxId ?? 0` (not `?? null`, review fix 2): a scene with ZERO interactions
  // at load must still baseline to a real number — interaction ids are DB pks
  // and never 0, so 0 is a safe "baselined empty" sentinel. `null` would be
  // indistinguishable from "baseline effect hasn't run yet", which would make
  // `countUnread` fall through to its no-baseline branch and stay silently
  // unbadged for that scene's first message.
  //
  // Gated on the per-puppet Redux `sceneBaselineId == null` (review fix 3),
  // NOT a single scalar ref keyed only by sceneId: a ref keyed on sceneId
  // alone has two bugs with multiple puppets — (1) puppet A (scene X,
  // baselined) -> puppet B (scene Y) -> back to puppet A (still scene X)
  // re-triggers the effect (the ref now holds "Y", not "X") and WIPES A's
  // already-accumulated unread by re-baselining to the current max id; (2)
  // puppet A and puppet B in the SAME scene X: A's switch already set the
  // ref to "X", so B's own turn never runs the effect at all and B's
  // Redux `sceneBaselineId` starves at its initial `null` forever. Reading
  // the per-puppet Redux value directly sidesteps both — it's already keyed
  // by character (`sessions[active]`), and `setSessionScene` nulls it out
  // exactly when that puppet's own scene id changes (see gameSlice.ts).
  useEffect(() => {
    if (!sceneId || !active) return;
    if (activeSession?.sceneBaselineId != null) return;
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      const id = Number(interaction.id);
      if (maxId === undefined || id > maxId) maxId = id;
    }
    dispatch(setSceneBaseline({ character: active, baselineId: maxId ?? 0 }));
  }, [sceneId, active, activeSession?.sceneBaselineId, allInteractions, dispatch]);

  // Threading filter/mute reset on scene change or puppet switch (#2156 review
  // fix): `useThreading`'s selectedThreadKey/enabledThreadKeys/hiddenPersonaIds
  // are local component state that otherwise never resets across renders —
  // GamePage is a single long-lived composition root, unlike SceneDetailPage
  // (a route change there remounts the whole tree for free). Without this, a
  // thread filter or muted participant picked in a PREVIOUS scene/puppet
  // context silently keeps hiding interactions in a new one, especially when
  // the new context happens to reuse an identical thread key (e.g. two
  // puppets in the same room). Keyed on the same `[active, sceneId]` pair the
  // baseline effect above uses.
  const threadingResetForNewScene = threading.resetForNewScene;
  useEffect(() => {
    threadingResetForNewScene();
  }, [active, sceneId, threadingResetForNewScene]);

  // Continuously mark the SELECTED thread seen as its interactions grow — this is
  // the thread the player is actively viewing, so it never accumulates unread.
  // Unselected threads are left alone and accumulate unread from the baseline above.
  useEffect(() => {
    if (!sceneId || !active) return;
    const selectedKey = threading.selectedThreadKey;
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      if (getThreadKey(interaction) !== selectedKey) continue;
      const id = Number(interaction.id);
      if (maxId === undefined || id > maxId) maxId = id;
    }
    if (maxId !== undefined) {
      dispatch(markThreadSeen({ character: active, threadKey: selectedKey, interactionId: maxId }));
    }
  }, [sceneId, active, allInteractions, threading.selectedThreadKey, dispatch]);

  // Mirrors SceneInteractionPanel's handleThreadClick (#2156 review fix): a
  // thread click toggles that thread's inclusion in the enabled-thread set
  // (which is what useThreading.filteredInteractions actually narrows on),
  // not just the "selected" highlight — otherwise the feed never changes.
  const handleThreadClick = (key: string) => {
    threading.toggleThreadVisibility(key);
    const thread = threading.threads.find((t) => t.key === key);
    if (thread) {
      setComposerMode(threadToComposerMode(thread, roomName));
    }
  };

  // Scene toolset (#2156 Task 6) — GamePage is the composition root, so it
  // owns the same handler state SceneDetailPage.tsx:120-178 owns, mirrored
  // exactly: consent, places, pending action attachments, and the action
  // panel. `PlaceBar`'s `sceneId` prop is actually used as the ROOM id in its
  // `fetchPlaces(?room=)` query (confirmed by reading PlaceBar.tsx +
  // actionQueries.ts) — so /game passes the real room id (`roomData.id`),
  // not the scene id. (`SceneDetailPage` passes the scene id, which is a
  // pre-existing latent bug in the places query on that page — left
  // untouched here; see the task report.)
  const placesRoomId = sceneId && roomData ? String(roomData.id) : undefined;

  // `isAtPlace` (#2156): derived from the SAME `['scene-places', placesRoomId]`
  // query key `PlaceBar` uses below, so React Query's cache dedupes the two
  // fetches into one (query-reuse, chosen over a callback-prop approach per
  // the task brief).
  const { data: placesData } = useQuery({
    queryKey: ['scene-places', placesRoomId],
    queryFn: () => fetchPlaces(placesRoomId!),
    enabled: !!placesRoomId,
  });
  const isAtPlace = placesData?.results?.some((place) => place.viewer_is_present) ?? false;

  // Pending unlinked actions for the chip strip — only fetched once a scene
  // is active (personaId gated to null otherwise disables the query).
  const { data: pendingActions } = usePendingUnlinkedActions(
    sceneId ?? '',
    sceneId ? personaId : null
  );
  const pendingActionIds = useMemo(() => pendingActions.map((a) => a.id), [pendingActions]);

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

  const [targetToAppend, setPendingTarget] = useState<string | null>(null);
  const [actionAttachment, setActionAttachment] = useState<ActionAttachmentInfo | null>(null);
  const queryClient = useQueryClient();

  const submitAction = useMutation({
    mutationFn: (action: ActionAttachmentInfo) =>
      createActionRequest(sceneId ?? '', {
        action_key: action.actionKey,
        target_persona_id: action.targetPersonaId,
        technique_id: action.techniqueId,
      }),
    onSuccess: () => {
      setActionAttachment(null);
      // No 'scene-messages' invalidation here (#2156 review fix): nothing in
      // this codebase ever queries that key — the scene feed here is
      // `useSceneInteractions`, which merges the WS-pushed interaction with no
      // React Query cache to invalidate. The stale call was dead on arrival.
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
    onError: () => {
      // Keep the attachment so the user can retry.
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

  if (!account) {
    return (
      <div className="mx-auto max-w-sm text-center">
        <p className="mb-4">You must be logged in to access the game.</p>
        <div className="flex justify-center gap-4">
          <Link to="/login" className="text-blue-500 hover:underline">
            Log in
          </Link>
          <Link to="/register" className="text-blue-500 hover:underline">
            Register
          </Link>
        </div>
      </div>
    );
  }

  // The tab label mirrors whatever is currently focused. While focused
  // on the room, fall back to the room name; defaults to "Room" when
  // there's no active session yet.
  let roomTabLabel = 'Room';
  switch (focus.current.kind) {
    case 'room':
      roomTabLabel = focus.current.room?.name ?? roomData?.name ?? 'Room';
      break;
    case 'character':
      roomTabLabel = focus.current.character.name;
      break;
    case 'item':
      roomTabLabel = focus.current.item.name;
      break;
  }

  return (
    <>
      <GameLayout
        topBar={<GameTopBar characters={characters} />}
        leftSidebar={
          <ConversationSidebar
            threading={sceneId ? threading : undefined}
            onThreadClick={handleThreadClick}
          />
        }
        center={
          <>
            {/* Scene toolset (#2156 Task 6) — mirrors SceneDetailPage.tsx:120-178's
                props exactly. Placement differs deliberately from the record page:
                ConsentPrompt sits above the center feed here; PlaceBar sits directly
                above the composer (passed into GameWindow, rendered just before
                CommandInput); ActionPanel is a `fixed` floating panel, so its DOM
                position doesn't matter. */}
            {sceneId && <ConsentPrompt sceneId={sceneId} />}
            <GameWindow
              characters={characters}
              sceneFeed={
                sceneId
                  ? {
                      sceneId,
                      interactions: threading.filteredInteractions,
                      hasNextPage,
                      fetchNextPage,
                    }
                  : undefined
              }
              composerMode={composerMode}
              onModeChange={setComposerMode}
              personaId={personaId}
              onAvatarClick={setCardPersona}
              onAddTarget={setPendingTarget}
              onAttachAction={handleActionAttach}
              targetToAppend={targetToAppend}
              onTargetConsumed={handleTargetConsumed}
              actionAttachment={actionAttachment}
              onActionAttach={handleActionAttach}
              onActionDetach={handleActionDetach}
              onSubmitAction={handleSubmitAction}
              pendingActionIds={pendingActionIds}
              detachedActionIds={detachedActionIds}
              onPoseSubmitted={handlePoseSubmitted}
              isAtPlace={isAtPlace}
              placeBar={placesRoomId ? <PlaceBar sceneId={placesRoomId} /> : undefined}
              pendingAttachments={
                sceneId ? (
                  <PendingActionAttachments
                    sceneId={sceneId}
                    personaId={personaId}
                    detachedIds={detachedActionIds}
                    onDetach={handleDetach}
                    onUndoDetach={handleUndoDetach}
                  />
                ) : undefined
              }
            />
            {sceneId && <ActionPanel sceneId={sceneId} />}
          </>
        }
        rightSidebar={
          <SidebarTabPanel
            roomTabLabel={roomTabLabel}
            roomPanel={
              <FocusPanel
                focus={focus}
                roomCharacter={active}
                roomData={roomData}
                sceneData={sceneData}
                hasActiveEncounter={hasActiveEncounter}
                hasActiveBattle={hasActiveBattle}
              />
            }
            storiesPanel={<StoryTray roomKey={roomData?.name ?? 'nowhere'} />}
            eventsPanel={<EventsSidebarPanel />}
            presencePanel={<PresencePanel />}
            statusPanel={
              activeCharacterId ? (
                <StatusPanel characterId={activeCharacterId} characterName={active ?? undefined} />
              ) : undefined
            }
            inventoryPanel={
              activeCharacterId ? (
                <InventorySidebarPanel characterId={activeCharacterId} />
              ) : undefined
            }
            journalPanel={<JournalTab />}
          />
        }
      />
      <CharacterCardDrawer
        persona={cardPersona}
        onClose={() => setCardPersona(null)}
        viewerEntryId={viewerEntryId}
        onWhisper={handleWhisper}
      />
    </>
  );
}
