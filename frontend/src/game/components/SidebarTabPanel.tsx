import { type ReactNode, useCallback, useState } from 'react';
import {
  Activity,
  Backpack,
  BookOpen,
  Calendar,
  ChevronDown,
  ChevronRight,
  PenLine,
  Scroll,
  Ship,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface SidebarTabPanelProps {
  roomPanel: ReactNode;
  eventsPanel: ReactNode;
  /** #885 story tray — the player's active missions, live where they stand. */
  storiesPanel?: ReactNode;
  codexPanel?: ReactNode;
  /** #1463 presence tab — who's online + where (coloured area paths). */
  presencePanel?: ReactNode;
  /** #1446 qualitative status tab — health/fatigue/anima as words, coin + AP as numbers. */
  statusPanel?: ReactNode;
  /** #1446 read-only carried-items tab — the sheet describes; the scene does. */
  inventoryPanel?: ReactNode;
  /** #2160 journal tab — compose + the player's 5 most recent entries. */
  journalPanel?: ReactNode;
  /** #2352 voyage panel — plan, depart, and track overworld travel. */
  travelPanel?: ReactNode;
  /**
   * What the way back names. Defaults to ``"Room"``; the parent passes the
   * currently-focused subject (the room, or a character or item drilled
   * into), so a section's "← <name>" control says where it returns to. Long
   * names are visually truncated; the full label stays in the ``title``.
   */
  roomTabLabel?: string;
  /** Controlled by `GamePage` (#3761) so a top-bar banner can jump straight to the room. */
  activeTab: string;
  onTabChange: (tab: string) => void;
}

/** The eight reference sections under the Actions fold, in the demo's order. */
const SECTIONS: Array<{ key: string; label: string; Icon: typeof Users }> = [
  { key: 'who', label: 'Who', Icon: Users },
  { key: 'stories', label: 'Stories', Icon: Scroll },
  { key: 'events', label: 'Events', Icon: Calendar },
  { key: 'codex', label: 'Codex', Icon: BookOpen },
  { key: 'status', label: 'Status', Icon: Activity },
  { key: 'inventory', label: 'Items', Icon: Backpack },
  { key: 'journal', label: 'Journal', Icon: PenLine },
  { key: 'travel', label: 'Travel', Icon: Ship },
];

/**
 * The Here panel's body (#3856 PR 3, the approved demo's side panel): the room
 * view with an "Actions" fold at its foot holding the eight reference sections
 * as a grid, open by default and folding on its arrow; pressing a section
 * shows it in place of the room with a "← <room>" way back at its top. It
 * replaces the nine-trigger tab row that used to sit above the room. Every
 * section keeps its panel and mounts lazily, on first open, as before.
 */
export function SidebarTabPanel({
  roomPanel,
  eventsPanel,
  storiesPanel,
  codexPanel,
  presencePanel,
  statusPanel,
  inventoryPanel,
  journalPanel,
  travelPanel,
  roomTabLabel,
  activeTab,
  onTabChange,
}: SidebarTabPanelProps) {
  // Seeded once from the mount-time `activeTab` — safe today because
  // `GamePage`'s `jumpToCombat` (#3761) only ever sets `activeTab` to 'room'
  // (this component's own mount default), so it's already activated. A
  // future caller that drives `activeTab` externally to some OTHER,
  // never-opened section would need to update `activatedTabs` too, or that
  // section's panel would never mount.
  const [activatedTabs, setActivatedTabs] = useState<Set<string>>(new Set([activeTab]));
  const [foldOpen, setFoldOpen] = useState(true);

  const handleTabChange = useCallback(
    (value: string) => {
      onTabChange(value);
      setActivatedTabs((prev) => {
        if (prev.has(value)) return prev;
        const next = new Set(prev);
        next.add(value);
        return next;
      });
    },
    [onTabChange]
  );

  const label = roomTabLabel ?? 'Room';

  if (activeTab !== 'room') {
    return (
      <div className="flex h-full flex-col">
        <button
          type="button"
          className="flex min-h-11 w-full items-center gap-1 px-3 text-left text-xs text-muted-foreground hover:text-foreground"
          title={label}
          onClick={() => handleTabChange('room')}
        >
          <span aria-hidden="true">←</span>
          <span className="truncate">{label}</span>
        </button>
        <div className="min-h-0 flex-1">
          {sectionContent(activeTab, activatedTabs, {
            eventsPanel,
            storiesPanel,
            codexPanel,
            presencePanel,
            statusPanel,
            inventoryPanel,
            journalPanel,
            travelPanel,
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">{roomPanel}</div>
      <details
        open={foldOpen}
        onToggle={(event) => setFoldOpen((event.target as HTMLDetailsElement).open)}
        className="border-t bg-muted/40"
        data-testid="actions-fold"
      >
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between px-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground [&::-webkit-details-marker]:hidden">
          Actions
          {foldOpen ? (
            <ChevronDown aria-hidden="true" className="h-3 w-3" />
          ) : (
            <ChevronRight aria-hidden="true" className="h-3 w-3" />
          )}
        </summary>
        <div className="grid grid-cols-3 gap-0.5 px-2 pb-2">
          {SECTIONS.map(({ key, label: name, Icon }) => (
            <button
              key={key}
              type="button"
              className={cn(
                'flex min-h-11 items-center gap-1.5 rounded px-2 text-left text-xs',
                'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
              )}
              onClick={() => handleTabChange(key)}
            >
              <Icon aria-hidden="true" className="h-3 w-3 shrink-0 opacity-60" />
              {name}
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}

type SectionPanels = Pick<
  SidebarTabPanelProps,
  | 'eventsPanel'
  | 'storiesPanel'
  | 'codexPanel'
  | 'presencePanel'
  | 'statusPanel'
  | 'inventoryPanel'
  | 'journalPanel'
  | 'travelPanel'
>;

function quiet(text: string, padded = true): ReactNode {
  return <p className={cn('text-sm text-muted-foreground', padded && 'p-3')}>{text}</p>;
}

/** One section's panel (or its quiet fallback), mounted only once it has been opened. */
function sectionContent(tab: string, activated: Set<string>, panels: SectionPanels): ReactNode {
  if (!activated.has(tab)) return null;
  switch (tab) {
    case 'who':
      return panels.presencePanel ?? quiet('No presence to show.');
    case 'stories':
      return panels.storiesPanel ?? quiet('No stories to show.');
    case 'events':
      return panels.eventsPanel;
    case 'codex':
      return <div className="p-3">{panels.codexPanel ?? quiet('Codex coming soon.', false)}</div>;
    case 'status':
      return <div className="p-3">{panels.statusPanel ?? quiet('No status to show.', false)}</div>;
    case 'inventory':
      return <div className="p-3">{panels.inventoryPanel ?? quiet('Nothing carried.', false)}</div>;
    case 'journal':
      return panels.journalPanel ?? quiet('No journal to show.');
    case 'travel':
      return panels.travelPanel ?? quiet('No travel to show.');
    default:
      return null;
  }
}
