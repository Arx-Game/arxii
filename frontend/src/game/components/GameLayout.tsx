import { useState, type ReactNode } from 'react';
import { usePageBackgrounds, pageBackgroundStyle } from '@/hooks/usePageBackgrounds';

interface GameLayoutProps {
  topBar: ReactNode;
  center: ReactNode;
  /** The single contextual sidebar. */
  sidebar?: ReactNode;
  /** Kept as a compatibility alias while callers migrate. */
  leftSidebar?: ReactNode;
  /** Deprecated compatibility input; it is never rendered as a second column. */
  rightSidebar?: ReactNode;
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
}: GameLayoutProps) {
  const { data: backgrounds } = usePageBackgrounds();
  const [mobilePane, setMobilePane] = useState<'story' | 'sidebar'>('story');
  const contextualSidebar = sidebar ?? rightSidebar ?? leftSidebar;
  return (
    <div
      className="flex min-h-0 min-w-0 flex-1 flex-col"
      style={pageBackgroundStyle(backgrounds, 'game_client', 'Game Client')}
    >
      {topBar}
      <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_clamp(240px,280px,360px)]">
        <div
          className={`min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background lg:flex ${mobilePane !== 'story' ? 'hidden' : 'flex'}`}
        >
          {center}
        </div>
        <div
          className={`min-h-0 overflow-hidden border-l bg-card lg:flex lg:flex-col ${mobilePane !== 'sidebar' ? 'hidden' : 'flex'}`}
        >
          {contextualSidebar}
        </div>
      </div>
      <nav className="flex shrink-0 border-t bg-card p-1 lg:hidden" aria-label="Play panes">
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
