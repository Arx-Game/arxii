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
  RAIL_MAX,
  RAIL_MIN,
  RAIL_STRIP_WIDTH,
  loadPlayPreferences,
  savePlayPreferences,
  usePlayPreferences,
  type SidebarSide,
} from '../playPreferences';

type MobilePane = 'rail' | 'story' | 'sidebar';

interface GameLayoutProps {
  topBar: ReactNode;
  center: ReactNode;
  /** The single contextual sidebar. */
  sidebar?: ReactNode;
  /** The conversation rail (#4129), the far-left column; absent, the shell is two columns. */
  rail?: ReactNode;
  accountId?: number | null;
}

/**
 * App shell for play (#3758, #4129): the conversation rail on the far left, one
 * wide reader/composer, and one contextual sidebar. At narrow widths the user
 * explicitly switches panes instead of losing any of them.
 */
export function GameLayout({ topBar, center, sidebar, rail, accountId }: GameLayoutProps) {
  const { data: backgrounds } = usePageBackgrounds();
  const [mobilePane, setMobilePane] = useState<MobilePane>('story');
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_PLAY_PREFERENCES.sidebarWidth);
  const [sidebarSide, setSidebarSide] = useState<SidebarSide>(DEFAULT_PLAY_PREFERENCES.sidebarSide);
  // The rail's width and folded state live in the shared preferences store, so
  // the rail's own « control and this column agree without an event between them.
  const { preferences, update } = usePlayPreferences(accountId);
  const railWidth = preferences.railCollapsed ? RAIL_STRIP_WIDTH : preferences.railWidth;

  useEffect(() => {
    const stored = loadPlayPreferences(accountId);
    setSidebarWidth(stored.sidebarWidth);
    setSidebarSide(stored.sidebarSide);
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<typeof stored>).detail;
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
        if (!savePlayPreferences({ ...stored, sidebarWidth: width }, accountId)) {
          window.dispatchEvent(new Event('arx-play-storage-warning'));
        }
      } catch {
        // Layout remains usable when storage is unavailable.
      }
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const clampRail = (width: number) => Math.min(RAIL_MAX, Math.max(RAIL_MIN, width));
  const resizeRail = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const origin = event.clientX;
    const initial = preferences.railWidth;
    let latestWidth = initial;
    const onMove = (move: globalThis.PointerEvent) => {
      latestWidth = clampRail(initial + move.clientX - origin);
      update({ railWidth: latestWidth });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const style = {
    '--play-sidebar-width': `${sidebarWidth}px`,
    '--play-rail-width': rail ? `${railWidth}px` : '0px',
  } as CSSProperties;
  const paneButton = (pane: MobilePane, label: string) => (
    <button
      type="button"
      aria-pressed={mobilePane === pane}
      onClick={() => setMobilePane(pane)}
      className="min-h-11 flex-1 rounded text-sm"
    >
      {label}
    </button>
  );
  return (
    <div
      className="flex min-h-0 min-h-[100dvh] min-w-0 flex-1 flex-col"
      style={pageBackgroundStyle(backgrounds, 'game_client', 'Game Client')}
      data-sidebar-side={sidebarSide}
      data-sidebar-width={sidebarWidth}
      data-rail-width={rail ? railWidth : undefined}
    >
      {topBar}
      <div
        className="play-workspace flex min-h-0 flex-1 flex-col"
        style={style}
        data-sidebar-side={sidebarSide}
      >
        {rail && (
          <div
            className={`play-rail-pane relative min-h-0 flex-1 overflow-hidden border-r bg-card ${mobilePane !== 'rail' ? 'hidden' : 'flex'}`}
            data-testid="play-rail-pane"
          >
            {rail}
            {!preferences.railCollapsed && (
              <button
                type="button"
                aria-label="Resize the rail"
                aria-valuemin={RAIL_MIN}
                aria-valuemax={RAIL_MAX}
                aria-valuenow={preferences.railWidth}
                aria-valuetext={`${preferences.railWidth}px`}
                data-testid="rail-resize"
                aria-orientation="vertical"
                role="separator"
                className="play-sidebar-resize absolute right-0 top-0 z-10 h-full w-3 cursor-col-resize touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onPointerDown={resizeRail}
                onKeyDown={(event) => {
                  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
                  event.preventDefault();
                  const delta = event.key === 'ArrowLeft' ? -8 : 8;
                  update({ railWidth: clampRail(preferences.railWidth + delta) });
                }}
              />
            )}
          </div>
        )}
        <div
          className={`play-story-pane min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background ${mobilePane !== 'story' ? 'hidden' : 'flex'}`}
          style={{ order: sidebarSide === 'left' ? 1 : 0 }}
        >
          {center}
        </div>
        <div
          className={`play-sidebar-pane relative min-h-0 flex-1 overflow-hidden bg-card ${sidebarSide === 'left' ? 'border-r' : 'border-l'} ${mobilePane !== 'sidebar' ? 'hidden' : 'flex'}`}
          style={{ order: sidebarSide === 'left' ? 0 : 1 }}
        >
          <button
            type="button"
            aria-label="Resize sidebar"
            aria-valuemin={240}
            aria-valuemax={360}
            aria-valuenow={sidebarWidth}
            aria-valuetext={`${sidebarWidth}px`}
            data-testid="sidebar-resize"
            aria-orientation="vertical"
            role="separator"
            className={`play-sidebar-resize absolute top-0 z-10 h-full w-11 cursor-col-resize touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${sidebarSide === 'left' ? 'right-0' : 'left-0'}`}
            onPointerDown={resizeSidebar}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
              event.preventDefault();
              const direction = event.key === 'ArrowLeft' ? -1 : 1;
              const delta = (sidebarSide === 'right' ? -direction : direction) * 8;
              const nextWidth = Math.min(360, Math.max(240, sidebarWidth + delta));
              setSidebarWidth(nextWidth);
              if (
                !savePlayPreferences(
                  { ...loadPlayPreferences(accountId), sidebarWidth: nextWidth },
                  accountId
                )
              ) {
                window.dispatchEvent(new Event('arx-play-storage-warning'));
              }
            }}
          />
          {sidebar}
        </div>
      </div>
      <nav className="play-mobile-nav flex shrink-0 border-t bg-card p-1" aria-label="Play panes">
        {rail && paneButton('rail', 'Rail')}
        {paneButton('story', 'Story')}
        {paneButton('sidebar', 'Sidebar')}
      </nav>
    </div>
  );
}
