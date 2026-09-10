import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { NarrativeMessageReader } from './NarrativeMessageReader';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { ConversationTabStrip, type ConversationTabStripProps } from './ConversationTabStrip';
import { SystemLane } from './SystemLane';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession } from '@/store/gameSlice';
import { useSelectCharacterMutation } from '@/roster/queries';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import { actingPersonaId } from '@/roster/persona';
import type { MyRosterEntry } from '@/roster/types';
import { sessionAttention } from '@/game/attention';

/**
 * Two-tier attention indicator (#2166 Decision 4a) on a puppet session tab —
 * direct (unseen whisper/@-target aimed at that character) badges a small
 * red numeric count, mirroring `ConversationTabStrip`'s `UnreadBadge`;
 * ambient (any other unread) shows a muted dot; neither renders nothing.
 */
function AttentionBadge({ direct, ambient }: { direct: number; ambient: boolean }) {
  if (direct > 0) {
    return (
      <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
        {direct}
      </span>
    );
  }
  if (ambient) {
    return (
      <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-muted-foreground/60" />
    );
  }
  return null;
}

/** The active scene's live feed, composed once by `GamePage` (#2156). */
export interface GameWindowSceneFeed {
  sceneId: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
}

interface GameWindowProps {
  characters: MyRosterEntry[];
  /** When present, the center column renders the threaded scene reader. */
  sceneFeed?: GameWindowSceneFeed;
  composerMode?: ComposerMode;
  onModeChange: (mode: ComposerMode) => void;
  /** The active character's persona id — lifted to GamePage to dedupe the roster query (#2156). */
  personaId: number | null;
  /** Avatar identity-click affordance (#2156) — opens the character-card drawer (Task 7). */
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
  /**
   * Scene toolset plumbing (#2156, Task 6) — GamePage is the composition root
   * that owns this state (mirroring `SceneDetailPage`'s handler state); these
   * are threaded straight through to `SceneMessages` and `CommandInput` since
   * both live inside this component.
   */
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  targetToAppend?: string | null;
  onTargetConsumed?: () => void;
  actionAttachment?: ActionAttachmentInfo | null;
  onActionAttach?: (action: ActionAttachmentInfo) => void;
  onActionDetach?: () => void;
  onSubmitAction?: (action: ActionAttachmentInfo) => void;
  pendingActionIds?: number[];
  detachedActionIds?: number[];
  onPoseSubmitted?: () => void;
  /** Explicit parent pose selected by the reader. */
  onReply?: (interaction: Interaction) => void;
  replyTarget?: Interaction | null;
  onCancelReply?: () => void;
  /** Stable account scope for per-tab drafts. */
  draftScopePrefix?: string;
  /** Whether the viewer's persona is present at a Place in this scene (#2156) — gates `tt`. */
  isAtPlace?: boolean;
  /** `PlaceBar`, rendered directly above the composer (#2156). */
  placeBar?: ReactNode;
  /** `TavernGameWidget`, rendered alongside PlaceBar (#3292). */
  tavernGameWidget?: ReactNode;
  /** `SpeakerQueueBar`, rendered alongside PlaceBar (#2356). */
  speakerQueueBar?: ReactNode;
  /** `PendingActionAttachments`, rendered directly above the composer (#2156). */
  pendingAttachments?: ReactNode;
  /** Open conversation tabs (#2165); absent = no strip, plain feed. */
  conversationTabs?: ConversationTabStripProps;
  /** "Speaking as" identity chip (#2166 Decision 3) — threaded straight to `CommandInput`. */
  speakingAs?: { name: string; thumbnailUrl: string | null };
  /** Read-only historical reference shown in the same reader. */
  reference?: { kind: string; key: string; title: string } | null;
  onReturnToLive?: () => void;
  referenceUnavailable?: boolean;
  referenceLoading?: boolean;
}

export function GameWindow({
  characters,
  sceneFeed,
  composerMode,
  onModeChange,
  personaId,
  onAvatarClick,
  onAddTarget,
  onAttachAction,
  targetToAppend,
  onTargetConsumed,
  actionAttachment,
  onActionAttach,
  onActionDetach,
  onSubmitAction,
  pendingActionIds,
  detachedActionIds,
  onPoseSubmitted,
  onReply,
  replyTarget,
  onCancelReply,
  draftScopePrefix,
  isAtPlace,
  placeBar,
  tavernGameWidget,
  speakerQueueBar,
  pendingAttachments,
  conversationTabs,
  speakingAs,
  reference,
  onReturnToLive,
  referenceUnavailable,
  referenceLoading = false,
}: GameWindowProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);
  const selectCharacter = useSelectCharacterMutation();

  // #2165 per-tab scroll: remember each tab's scroll offset, restore on
  // switch, and stick to bottom while the reader is already at the bottom
  // (adapted from ChatWindow's autoScroll pattern).
  const feedScrollRef = useRef<HTMLDivElement>(null);
  const scrollPositionsRef = useRef(new Map<string, number>());
  const pinnedRef = useRef(true);
  const activeConvKey = conversationTabs?.activeKey ?? 'room';
  const interactionCount = sceneFeed?.interactions.length ?? 0;

  useEffect(() => {
    const el = feedScrollRef.current;
    if (!el) return;
    const saved = scrollPositionsRef.current.get(activeConvKey);
    if (saved !== undefined) {
      el.scrollTop = saved;
      pinnedRef.current = el.scrollHeight - saved - el.clientHeight < 8;
    } else {
      el.scrollTop = el.scrollHeight;
      pinnedRef.current = true;
    }
    // Prune scroll offsets for tabs that are no longer open (#2165 review
    // fold-in) — otherwise a closed tab's entry lingers in the map forever.
    const liveKeys = new Set(['room', ...(conversationTabs?.tabs.map((t) => t.key) ?? [])]);
    for (const key of scrollPositionsRef.current.keys()) {
      if (!liveKeys.has(key)) scrollPositionsRef.current.delete(key);
    }
  }, [activeConvKey, conversationTabs?.tabs]);

  useEffect(() => {
    const el = feedScrollRef.current;
    if (el && pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [interactionCount, activeConvKey]);

  const handleFeedScroll = () => {
    const el = feedScrollRef.current;
    if (!el) return;
    scrollPositionsRef.current.set(activeConvKey, el.scrollTop);
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  };

  if (characters.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-sm">
          You have no active characters. Visit the{' '}
          <Link to="/roster" className="underline">
            roster
          </Link>{' '}
          to apply for one.
        </p>
      </div>
    );
  }

  // #3412 review fix: `active` can now be hydrated from the server on a hard
  // reload with no `sessions[active]` entry yet — selection isn't presence,
  // so hydration never starts a session. Treat "active but not connected
  // yet" the same as "no active" here (GameTopBar's active avatar is the
  // affordance to actually connect); every access below this line can
  // otherwise assume `session` exists.
  const session = active ? sessions[active] : undefined;
  if (!active || !session) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-dashed p-8 text-center">
          <h1 className="font-serif text-2xl">Enter the world</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Choose a character above to begin. Your surroundings and story will appear here.
          </p>
        </div>
      </div>
    );
  }

  const sessionNames = Object.keys(sessions);
  const awaitingRoom = !session.room && !sceneFeed;

  const handleTabClick = (name: MyRosterEntry['name']) => {
    // #3412 — persist the selection server-side ALONGSIDE the existing
    // puppeting behavior below, never replacing it.
    const entryId = characters.find((c) => c.name === name)?.id;
    if (entryId !== undefined) {
      selectCharacter.mutate(entryId);
    }
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      connect(name);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {reference && (
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b bg-amber-500/10 px-4 py-2 text-sm"
          role="status"
        >
          <span>Reading history · {reference.title}</span>
          <button
            type="button"
            className="rounded border px-3 py-1 text-xs font-medium"
            onClick={onReturnToLive}
          >
            Return to live
          </button>
        </div>
      )}
      {awaitingRoom && (
        <div
          className="shrink-0 border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground"
          role="status"
        >
          {session.isConnected
            ? 'Entering the world… waiting for a confirmed location. You can write while you wait.'
            : 'Connection lost. Your draft is safe; you can keep writing while we reconnect.'}
        </div>
      )}
      {sessionNames.length >= 2 && (
        <div className="mb-2 flex gap-2 border-b">
          {sessionNames.map((name) => {
            const personaId = actingPersonaId(characters.find((c) => c.name === name));
            const attention = sessionAttention(sessions[name], personaId);
            return (
              <button
                key={name}
                onClick={() => handleTabClick(name)}
                className={`relative rounded-t px-2 py-1 text-sm ${
                  active === name ? 'border-b-2 border-primary' : ''
                }`}
              >
                {name}
                {/* The active character's own attention already lives in
                    ConversationTabStrip's badges (#2166 review fold-in) — badging
                    its own already-highlighted puppet tab too is redundant/wrong. */}
                {name !== active && (
                  <AttentionBadge direct={attention.direct} ambient={attention.ambient} />
                )}
              </button>
            );
          })}
        </div>
      )}
      {sceneFeed && conversationTabs && <ConversationTabStrip {...conversationTabs} />}
      {sceneFeed ? (
        <>
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
            ref={feedScrollRef}
            onScroll={handleFeedScroll}
          >
            {referenceLoading && reference && (
              <div
                className="mx-auto my-8 max-w-md p-6 text-center text-muted-foreground"
                role="status"
              >
                Loading history…
              </div>
            )}
            {!referenceLoading && referenceUnavailable && reference && (
              <div
                className="mx-auto my-8 max-w-md rounded-lg border border-dashed p-6 text-center"
                role="alert"
              >
                <h2 className="font-serif text-xl">This pose is no longer available</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  The requested history cannot be shown with your current access.
                </p>
                <button
                  type="button"
                  className="mt-4 rounded border px-3 py-2 text-sm"
                  onClick={onReturnToLive}
                >
                  Return to live
                </button>
              </div>
            )}
            {!referenceLoading && !referenceUnavailable && (
              <ThreadedNarrativeReader
                sceneId={sceneFeed.sceneId}
                conversationKey={sceneFeed.sceneId}
                interactions={sceneFeed.interactions}
                hasNextPage={sceneFeed.hasNextPage}
                fetchNextPage={sceneFeed.fetchNextPage}
                onAvatarClick={onAvatarClick}
                onAddTarget={onAddTarget}
                onAttachAction={onAttachAction}
                onReply={onReply}
                readOnly={Boolean(reference)}
              />
            )}
          </div>
          {!reference && <SystemLane messages={session.messages} />}
        </>
      ) : (
        <NarrativeMessageReader messages={session.messages} />
      )}
      {placeBar}
      {tavernGameWidget}
      {speakerQueueBar}
      {pendingAttachments}
      {reference ? (
        <div className="shrink-0 border-t bg-card px-4 py-3 text-center text-xs text-muted-foreground">
          Draft preserved for your live conversation
        </div>
      ) : (
        <CommandInput
          character={active}
          sceneId={sceneFeed?.sceneId}
          personaId={personaId}
          composerMode={composerMode}
          onModeChange={onModeChange}
          targetToAppend={targetToAppend}
          onTargetConsumed={onTargetConsumed}
          actionAttachment={actionAttachment}
          onActionAttach={onActionAttach}
          onActionDetach={onActionDetach}
          onSubmitAction={onSubmitAction}
          pendingActionIds={pendingActionIds}
          detachedActionIds={detachedActionIds}
          onPoseSubmitted={onPoseSubmitted}
          isAtPlace={isAtPlace}
          speakingAs={speakingAs}
          replyTarget={replyTarget}
          onCancelReply={onCancelReply}
          submitOnEnter={false}
          draftScope={`${draftScopePrefix ?? 'account'}:${active}:${conversationTabs?.activeKey ?? 'room'}`}
          ready={session.isConnected && Boolean(session.room)}
        />
      )}
    </div>
  );
}
