import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { fetchScene, SceneDetail } from '../queries';
import { createActionRequest, fetchPlaces } from '../actionQueries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneInteractionPanel } from '../components/SceneInteractionPanel';
import { ActionPanel } from '../components/ActionPanel';
import { PlaceBar } from '../components/PlaceBar';
import { TavernGameWidget } from '../components/TavernGameWidget';
import { SpeakerQueueBar } from '../components/SpeakerQueueBar';
import { SceneTacticalMap } from '../components/SceneTacticalMap';
import { HighlightReel } from '../components/HighlightReel';
import { ConsentPrompt } from '../components/ConsentPrompt';
import { PrecapturePanel } from '../components/PrecapturePanel';
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
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { PendingActionAttachments } from '../components/PendingActionAttachments';
import { usePendingUnlinkedActions } from '../hooks/usePendingUnlinkedActions';
import { useBattleForSceneQuery } from '@/battles/queries';
import { RitualProposedChip } from '@/rituals/components/RitualProposedChip';
import { useEncounterForScene } from '@/combat/queries';
import { CombatRail } from '@/combat/components/CombatRail';
import { GMEncounterControls } from '@/combat/sections/GMEncounterControls';
import { GMStoryRail } from '../components/GMStoryRail';
import { ScenarioCard } from '../components/ScenarioCard';
import { LinkedStoriesPanel } from '@/crossover/components/LinkedStoriesPanel';
import {
  GMAdjudicationPanel,
  GM_TOOL_TABS,
  NON_COMBAT_GM_TOOL_TABS,
} from '../components/GMAdjudicationPanel';
import { SelfCheckPanel } from '../components/SelfCheckPanel';
import { CheckCallPromptCard } from '../components/CheckCallPromptCard';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';

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

  // Combat rail fold-in (#2197): combat now renders inline on the scene page
  // instead of a separate /scenes/:id/combat route — the fight never leaves
  // the room it's happening in. Two-column layout (matching the former
  // CombatScenePage's C-frame grid) only while an active encounter exists;
  // single column otherwise.
  const sceneIdNum = id ? Number(id) : 0;
  const { data: encounterListItem, isLoading: encounterLoading } = useEncounterForScene(sceneIdNum);
  const hasActiveEncounter = !encounterLoading && encounterListItem != null;
  const encounterId = encounterListItem?.id ?? 0;
  // GM story rail fold-in (#3434): shares the right-rail column with the
  // combat rail. Mounted whenever the viewer can GM this scene at all --
  // GMStoryRail itself renders the "no beat running" fallback when
  // scene.running_beat is null, so the grid doesn't collapse the moment a
  // GM's beat finishes.
  const showStoryRail = !!scene?.viewer_can_gm;

  // Scroll the rail into view the moment an encounter first appears
  // (none -> active transition) so a player mid-pose notices combat starting.
  const railRef = useRef<HTMLDivElement>(null);
  const wasActiveRef = useRef(false);
  useEffect(() => {
    if (hasActiveEncounter && !wasActiveRef.current) {
      railRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    wasActiveRef.current = hasActiveEncounter;
  }, [hasActiveEncounter]);
  const { data: battle } = useBattleForSceneQuery(id ? Number(id) : null);

  // Resolve the active character's primary persona id for submit_pose REST calls.
  // Also derives characterSheetId: CharacterSheet uses OneToOneField(primary_key=True)
  // to ObjectDB, so character_id === character_sheet pk.
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const personaId = actingPersonaId(activeEntry);
  const characterSheetId = activeEntry?.character_id ?? 0;
  // The active character's own RosterEntry id (#2156 Task 7) — the FriendButton's
  // `viewerEntryId` inside the character-card drawer.
  const viewerEntryId = activeEntry?.id ?? null;

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
      // 2026-07 audit: 'scene-messages' matched no query — the feed key is 'scene-interactions'.
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', id] });
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

  // The foldable part of the header (#3557): rendered inline when idle, inside
  // the "Scene tools" accordion during an encounter. Same order as before.
  // Folding remounts the subtree, so a local draft in SelfCheckPanel or
  // TavernGameWidget is lost at the tick an encounter starts; accepted in
  // ADR-0270. Prompts that need an answer never fold.
  const sceneTools = (
    <>
      {scene && <SceneLinesAndVeilsCard sceneId={id} />}
      {placesRoomId && <PlaceBar sceneId={placesRoomId} />}
      {placesRoomId && <TavernGameWidget roomId={placesRoomId} />}
      {placesRoomId && <SpeakerQueueBar roomId={placesRoomId} />}
      {/* One map during a fight: the rail's CombatTacticalMap draws the room
          with bystanders, so the header map unmounts (Set the Stage rides on
          it and is unavailable mid-fight by design; it returns with the map). */}
      {!hasActiveEncounter && <SceneTacticalMap sceneId={id} />}
      <HighlightReel sceneId={id} canGm={scene?.viewer_can_gm} />
      {/* GM "Start Encounter" affordance (#3067), only while no encounter is
          active; the active-encounter controls live in the rail's GM tab. */}
      {!encounterLoading && !hasActiveEncounter && (
        <GMEncounterControls
          sceneId={sceneIdNum}
          encounter={null}
          viewerCanGm={scene?.viewer_can_gm ?? false}
        />
      )}
      {scene && <LinkedStoriesPanel sceneId={id} />}
      {/* #3295 scene check invocation. The call-answer prompt keeps this slot
          when idle; during a fight it renders inline above the accordion. */}
      {isActive && !hasActiveEncounter && (
        <div className="mt-2">
          <CheckCallPromptCard />
        </div>
      )}
      {isActive && (
        <div className="mt-2">
          <SelfCheckPanel />
        </div>
      )}
      {scene?.viewer_can_gm && (
        <div className="mt-2">
          <GMAdjudicationPanel
            scene={scene}
            tabs={hasActiveEncounter ? NON_COMBAT_GM_TOOL_TABS : GM_TOOL_TABS}
          />
        </div>
      )}
    </>
  );

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
        {scene?.is_owner && <PrecapturePanel sceneId={id} />}
        {isActive && <ConsentPrompt sceneId={id} />}
        {isActive && <SineatingInbox />}
        {isActive && <SoulTetherRescuePrompt />}
        {isActive && <EntryFlourishOfferGate characterSheetId={characterSheetId} />}
        {/* #3557 combat layout. Everything above this line either needs an
            answer (consent, sineating, soul-tether, flourish) or is the scene's
            identity; it stays inline in both shapes. Below: while an encounter
            is active the header map yields to the rail's map (one map, with
            bystanders), the pending check-call prompt stays inline, and the
            rest of the stack folds behind one closed "Scene tools" accordion so
            the feed and composer sit under the title. Idle renders today's
            stack unchanged. */}
        {hasActiveEncounter ? (
          <>
            {isActive && (
              <div className="mt-2">
                <CheckCallPromptCard />
              </div>
            )}
            <Accordion
              type="single"
              collapsible
              className="mt-2"
              data-testid="scene-tools-accordion"
            >
              <AccordionItem value="scene-tools" className="border-b-0">
                <AccordionTrigger className="py-2 text-sm" data-testid="scene-tools-trigger">
                  Scene tools
                </AccordionTrigger>
                <AccordionContent>{sceneTools}</AccordionContent>
              </AccordionItem>
            </Accordion>
          </>
        ) : (
          sceneTools
        )}
      </div>

      {/* Combat rail fold-in (#2197): a two-column C-frame grid while an active
          encounter exists (or the GM story rail is shown); single column
          otherwise. The rail's GM tab (#3557) hosts the encounter controls. */}
      <div
        className={cn(
          'min-h-0 flex-1',
          hasActiveEncounter || showStoryRail
            ? 'grid grid-cols-[1fr_360px] gap-4 px-4 pb-4'
            : 'flex flex-col'
        )}
      >
        <div className="flex min-h-0 flex-1 flex-col" data-testid="scene-detail-left">
          {/* #3565 - the mission scenario a scene's beats run on; self-hides
              for non-participants, so it's mounted for every viewer. */}
          {scene && <ScenarioCard scene={scene} />}

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
                    speakingAs={
                      activeEntry
                        ? { name: activeEntry.name, thumbnailUrl: activeEntry.profile_picture_url }
                        : undefined
                    }
                  />
                </>
              )}
              <ActionPanel sceneId={id} />
            </div>
          )}
        </div>

        {(hasActiveEncounter || showStoryRail) && (
          <div
            ref={railRef}
            className="min-h-0 space-y-3 overflow-y-auto"
            data-testid="scene-detail-combat-rail"
          >
            {showStoryRail && scene && <GMStoryRail scene={scene} />}
            {hasActiveEncounter && (
              <CombatRail
                sceneId={sceneIdNum}
                encounterId={encounterId}
                viewerCanGm={scene?.viewer_can_gm ?? false}
                scene={scene}
              />
            )}
          </div>
        )}
      </div>
      <CharacterCardDrawer
        persona={cardPersona}
        onClose={() => setCardPersona(null)}
        viewerEntryId={viewerEntryId}
        onWhisper={handleWhisper}
      />
    </div>
  );
}
