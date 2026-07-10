import type { ReactNode } from 'react';
import { ChatWindow } from './ChatWindow';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { SystemLane } from './SystemLane';
import { SceneMessages } from '@/scenes/components/SceneMessages';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';

/** The active scene's live feed, composed once by `GamePage` (#2156). */
export interface GameWindowSceneFeed {
  sceneId: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
}

interface GameWindowProps {
  characters: MyRosterEntry[];
  /** When present, the center column renders the structured scene feed instead of ChatWindow. */
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
  /** Whether the viewer's persona is present at a Place in this scene (#2156) — gates `tt`. */
  isAtPlace?: boolean;
  /** `PlaceBar`, rendered directly above the composer (#2156). */
  placeBar?: ReactNode;
  /** `PendingActionAttachments`, rendered directly above the composer (#2156). */
  pendingAttachments?: ReactNode;
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
  isAtPlace,
  placeBar,
  pendingAttachments,
}: GameWindowProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);

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

  if (!active) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Select a character to begin.</p>
      </div>
    );
  }

  const session = sessions[active];
  const sessionNames = Object.keys(sessions);

  const handleTabClick = (name: MyRosterEntry['name']) => {
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      connect(name);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {sessionNames.length >= 2 && (
        <div className="mb-2 flex gap-2 border-b">
          {sessionNames.map((name) => (
            <button
              key={name}
              onClick={() => handleTabClick(name)}
              className={`relative rounded-t px-2 py-1 text-sm ${
                active === name ? 'border-b-2 border-primary' : ''
              }`}
            >
              {name}
              {sessions[name].unread > 0 && (
                <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500" />
              )}
            </button>
          ))}
        </div>
      )}
      {sceneFeed ? (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <SceneMessages
              sceneId={sceneFeed.sceneId}
              filteredInteractions={sceneFeed.interactions}
              onAvatarClick={onAvatarClick}
              onAddTarget={onAddTarget}
              onAttachAction={onAttachAction}
            />
            {sceneFeed.hasNextPage && (
              <button onClick={() => sceneFeed.fetchNextPage()} className="mt-4 px-4">
                Load More
              </button>
            )}
          </div>
          <SystemLane messages={session.messages} />
        </>
      ) : (
        <ChatWindow messages={session.messages} />
      )}
      {placeBar}
      {pendingAttachments}
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
      />
    </div>
  );
}
