import {
  useEffect,
  useState,
  type CSSProperties,
  type ReactNode,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { usePageBackgrounds, pageBackgroundStyle } from '@/hooks/usePageBackgrounds';
import {
  DEFAULT_PLAY_PREFERENCES,
  loadPlayPreferences,
  savePlayPreferences,
  type SidebarSide,
} from '../playPreferences';

interface GameLayoutProps {
  topBar: ReactNode;
  center: ReactNode;
  /** The single contextual sidebar. */
  sidebar?: ReactNode;
  /** Kept as a compatibility alias while callers migrate. */
  leftSidebar?: ReactNode;
  /** Deprecated compatibility input; it is never rendered as a second column. */
  rightSidebar?: ReactNode;
  accountId?: number | null;
}

/**
 * App shell for play: one wide reader/composer and one contextual sidebar.
 * At narrow widths the user explicitly switches panes instead of losing either.
 */
export function GameLayout({
  topBar,
  center,
  sidebar,
  leftSidebar,
  rightSidebar,
  accountId,
}: GameLayoutProps) {
  const { data: backgrounds } = usePageBackgrounds();
  const [mobilePane, setMobilePane] = useState<'story' | 'sidebar'>('story');
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_PLAY_PREFERENCES.sidebarWidth);
  const [sidebarSide, setSidebarSide] = useState<SidebarSide>(DEFAULT_PLAY_PREFERENCES.sidebarSide);
  const contextualSidebar = sidebar ?? rightSidebar ?? leftSidebar;

  useEffect(() => {
    const preferences = loadPlayPreferences(accountId);
    setSidebarWidth(preferences.sidebarWidth);
    setSidebarSide(preferences.sidebarSide);
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<typeof preferences>).detail;
      if (!detail) return;
      setSidebarWidth(detail.sidebarWidth);
      setSidebarSide(detail.sidebarSide);
    };
    window.addEventListener('arx-play-preferences', sync);
    return () => window.removeEventListener('arx-play-preferences', sync);
  }, [accountId]);

  const resizeSidebar = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const origin = event.clientX;
    const initial = sidebarWidth;
    let latestWidth = initial;
    const onMove = (move: globalThis.PointerEvent) => {
      const delta = sidebarSide === 'right' ? origin - move.clientX : move.clientX - origin;
      latestWidth = Math.min(360, Math.max(240, initial + delta));
      setSidebarWidth(latestWidth);
    };
    const onUp = () => {
      const width = latestWidth;
      try {
        const stored = loadPlayPreferences(accountId);
        savePlayPreferences({ ...stored, sidebarWidth: width }, accountId);
      } catch {
        // Layout remains usable when storage is unavailable.
      }
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const style = {
    '--play-sidebar-width': `${sidebarWidth}px`,
  } as CSSProperties;
  return (
    <div
      className="flex min-h-0 min-h-[100dvh] min-w-0 flex-1 flex-col"
      style={pageBackgroundStyle(backgrounds, 'game_client', 'Game Client')}
      data-sidebar-side={sidebarSide}
      data-sidebar-width={sidebarWidth}
    >
      {topBar}
      <div className="play-workspace flex min-h-0 flex-1 flex-col" style={style}>
        <div
          className={`play-story-pane min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background ${mobilePane !== 'story' ? 'hidden' : 'flex'}`}
          style={{ order: sidebarSide === 'left' ? 1 : 0 }}
        >
          {center}
        </div>
        <div
          className={`play-sidebar-pane relative min-h-0 overflow-hidden bg-card ${sidebarSide === 'left' ? 'border-r' : 'border-l'} ${mobilePane !== 'sidebar' ? 'hidden' : 'flex'}`}
          style={{ order: sidebarSide === 'left' ? 0 : 1 }}
        >
          <button
            type="button"
            aria-label="Resize sidebar"
            aria-valuemin={240}
            aria-valuemax={360}
            aria-valuenow={sidebarWidth}
            aria-orientation="vertical"
            role="separator"
            className={`absolute top-0 z-10 hidden h-full w-11 cursor-col-resize touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${sidebarSide === 'left' ? 'right-0' : 'left-0'}`}
            onPointerDown={resizeSidebar}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
              event.preventDefault();
              const delta = event.key === 'ArrowLeft' ? -8 : 8;
              const nextWidth = Math.min(360, Math.max(240, sidebarWidth + delta));
              setSidebarWidth(nextWidth);
              savePlayPreferences(
                { ...loadPlayPreferences(accountId), sidebarWidth: nextWidth },
                accountId
              );
            }}
          />
          {contextualSidebar}
        </div>
      </div>
      <nav className="play-mobile-nav flex shrink-0 border-t bg-card p-1" aria-label="Play panes">
        <button
          type="button"
          aria-pressed={mobilePane === 'story'}
          onClick={() => setMobilePane('story')}
          className="min-h-11 flex-1 rounded text-sm"
        >
          Story
        </button>
        <button
          type="button"
          aria-pressed={mobilePane === 'sidebar'}
          onClick={() => setMobilePane('sidebar')}
          className="min-h-11 flex-1 rounded text-sm"
        >
          Sidebar
        </button>
      </nav>
    </div>
  );
}
