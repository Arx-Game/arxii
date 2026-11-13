import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { Compass, History, MessagesSquare, Swords } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { HistoryNavigator } from './HistoryNavigator';
import { DisplaySettings } from './DisplaySettings';

export type SidebarMode = 'here' | 'history' | 'channels';

const NAV_COLUMNS = ['grid-cols-2', 'grid-cols-3', 'grid-cols-4'] as const;

interface PlaySidebarProps {
  here: ReactNode;
  /** The Guide's NPC cards (#4418): offers, notes, response. Shown above the Here panels. */
  npcCards?: ReactNode;
  accountId?: number | null;
  onOpenReference?: (ref: {
    kind: string;
    key: string;
    title: string;
    poseId?: string;
    timestamp?: string;
  }) => void;
  /** Controlled by `GamePage` (#3761) so a top-bar banner can also drive it. */
  mode: SidebarMode;
  onModeChange: (mode: SidebarMode) => void;
  /** Drives the 4th "Combat" nav button (#3761) — omitted or false hides it entirely. */
  hasActiveEncounter?: boolean;
  /** Required when `hasActiveEncounter` is true; the Combat button's click handler. */
  onJumpToCombat?: () => void;
  /** The Channels mode body (#3299); omitted hides the Channels button. */
  channels?: ReactNode;
  /** Unread across unmuted channels not set to Nothing; shown on the Channels button. */
  channelsUnread?: number;
}

/**
 * The one contextual sidebar for the narrative play workspace: Here, History
 * and Channels. Conversations live in the rail on the far left (#4129).
 */
export function PlaySidebar({
  here,
  npcCards,
  accountId,
  onOpenReference,
  mode,
  onModeChange,
  hasActiveEncounter,
  onJumpToCombat,
  channels,
  channelsUnread = 0,
}: PlaySidebarProps) {
  // #3759 review fix: the modes share ONE scroll container
  // (`play-sidebar-scroll`), so each mode needs its own remembered scroll
  // position, restored on switch — mirrors GameWindow.tsx's per-conversation
  // scrollPositionsRef pattern, adapted for these fixed modes. `useLayoutEffect` (not `useEffect`) matters
  // here specifically: these bodies are `hidden`-attribute siblings, not
  // swapped content, so the newly-shown body's layout (scrollHeight) is only
  // final once the browser has applied the `hidden` toggle — restoring after
  // paint would flash the wrong offset.
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollPositionsRef = useRef(new Map<SidebarMode, number>());

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = scrollPositionsRef.current.get(mode) ?? 0;
  }, [mode]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    scrollPositionsRef.current.set(mode, el.scrollTop);
  };

  const buttonCount = 2 + (channels ? 1 : 0) + (hasActiveEncounter ? 1 : 0);

  return (
    <aside className="flex h-full min-h-0 flex-col" aria-label="Play sidebar">
      <nav
        className={`grid shrink-0 gap-1 border-b p-2 ${NAV_COLUMNS[buttonCount - 2]}`}
        aria-label="Sidebar modes"
      >
        <button
          type="button"
          aria-current={mode === 'here' ? 'page' : undefined}
          onClick={() => onModeChange('here')}
          className={`flex min-h-11 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'here' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
        >
          <Compass className="h-3.5 w-3.5" />
          Here
        </button>
        <button
          type="button"
          aria-current={mode === 'history' ? 'page' : undefined}
          onClick={() => onModeChange('history')}
          className={`flex min-h-11 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'history' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
        >
          <History className="h-3.5 w-3.5" />
          History
        </button>
        {channels ? (
          <button
            type="button"
            aria-current={mode === 'channels' ? 'page' : undefined}
            onClick={() => onModeChange('channels')}
            className={`flex min-h-11 items-center justify-center gap-1 rounded px-2 text-xs ${mode === 'channels' ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60'}`}
          >
            <MessagesSquare className="h-3.5 w-3.5" />
            Channels
            {channelsUnread > 0 ? (
              <Badge
                variant="destructive"
                className="h-4 min-w-4 px-1 text-[10px]"
                data-testid="channels-unread-badge"
              >
                {channelsUnread}
              </Badge>
            ) : null}
          </button>
        ) : null}
        {hasActiveEncounter && (
          <button
            type="button"
            onClick={onJumpToCombat}
            className="flex min-h-11 items-center justify-center gap-1 rounded px-2 text-xs text-destructive hover:bg-accent/60"
          >
            <Swords className="h-3.5 w-3.5" />
            Combat
          </button>
        )}
      </nav>
      <div className="shrink-0 px-2 pb-1">
        <DisplaySettings accountId={accountId} />
      </div>
      <div
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
        data-testid="play-sidebar-scroll"
        ref={scrollRef}
        onScroll={handleScroll}
      >
        <div hidden={mode !== 'here'}>
          {npcCards}
          {here}
        </div>
        <div hidden={mode !== 'history'}>
          <HistoryNavigator onOpenReference={onOpenReference} />
        </div>
        {channels ? <div hidden={mode !== 'channels'}>{channels}</div> : null}
      </div>
    </aside>
  );
}
