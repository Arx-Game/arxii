import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { ChevronsLeft } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { PersonaMenu } from '@/scenes/components/PersonaMenu';
import type { ThreadPersona } from '@/scenes/hooks/useThreading';
import { usePlayPreferences } from '../playPreferences';
import { RAIL_KIND_WORDS, allRailRows, type RailGroups, type RailRow } from '../railRows';
import { cn } from '@/lib/utils';

/** The information-flow actions a person's row offers (#4128's per-character items). */
export interface RailPersonActions {
  minimizeAllFrom: (personaId: number) => void;
  hideAllFrom: (personaId: number) => void;
  expandAll: () => void;
  unhideAll: () => void;
}

interface ConversationRailProps {
  accountId?: number | null;
  groups: RailGroups;
  /** The selected row's key; null is All. */
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  personActions: RailPersonActions;
  /** The find box's text (#4129, decision 7), owned by the page with the feed it narrows. */
  find: string;
  onFindChange: (text: string) => void;
}

function Count({ count, label }: { count: number; label?: string }) {
  if (count <= 0) return null;
  return (
    <span
      className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs tabular-nums text-primary-foreground"
      data-testid="rail-count"
      title={label}
      aria-label={label ? `${count} unread in ${label}` : `${count} unread`}
    >
      {count}
    </span>
  );
}

interface PersonMenuState {
  at: { x: number; y: number };
  person: ThreadPersona;
}

/**
 * The sorting menu on a person's row (#4129, decision 5): the per-character
 * half of #4128's line menu, with nothing per line. Opened at the pointer by a
 * right-click on the row, anchored to a zero-size trigger placed there.
 */
function RailPersonMenu({
  state,
  onClose,
  actions,
}: {
  state: PersonMenuState | null;
  onClose: () => void;
  actions: RailPersonActions;
}) {
  const open = state !== null;
  useEffect(() => {
    if (!open) return;
    const swallow = (event: Event) => event.preventDefault();
    document.addEventListener('contextmenu', swallow);
    return () => document.removeEventListener('contextmenu', swallow);
  }, [open]);
  return (
    <DropdownMenu open={open} onOpenChange={(next) => !next && onClose()}>
      <DropdownMenuTrigger asChild>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute h-0 w-0"
          style={{ left: state?.at.x ?? 0, top: state?.at.y ?? 0 }}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        onCloseAutoFocus={(event) => event.preventDefault()}
        className="data-[state=closed]:!animate-none"
      >
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          {state?.person.name}
        </DropdownMenuLabel>
        <DropdownMenuItem onClick={() => state && actions.minimizeAllFrom(state.person.id)}>
          Minimize all from {state?.person.name}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => state && actions.hideAllFrom(state.person.id)}>
          Hide all from {state?.person.name}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={actions.expandAll}>Expand all</DropdownMenuItem>
        <DropdownMenuItem onClick={actions.unhideAll}>Unhide all</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Row({
  row,
  selected,
  onSelect,
  onPersonMenu,
}: {
  row: RailRow;
  selected: boolean;
  onSelect: () => void;
  onPersonMenu: (event: ReactMouseEvent<HTMLElement>, person: ThreadPersona) => void;
}) {
  const kindWord = RAIL_KIND_WORDS[row.kind];
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-md px-2 hover:bg-muted',
        selected && 'bg-accent font-semibold'
      )}
      data-testid="rail-row"
      data-rail-key={row.key}
      onContextMenu={row.person ? (event) => onPersonMenu(event, row.person!) : undefined}
    >
      {row.person && (
        <span className="flex shrink-0" data-testid="rail-face">
          <PersonaMenu
            personaId={row.person.id}
            personaName={row.person.name}
            thumbnailUrl={row.person.thumbnailUrl}
            leftClick
            contextMenu={false}
          >
            <span role="img" aria-label={row.person.name} className="flex">
              <PersonaAvatar
                source={{ name: row.person.name, thumbnailUrl: row.person.thumbnailUrl }}
                size="xs"
              />
            </span>
          </PersonaMenu>
        </span>
      )}
      <button
        type="button"
        aria-current={selected ? 'true' : undefined}
        onClick={onSelect}
        className="flex min-h-9 min-w-0 flex-1 items-center gap-2 py-1 text-left text-sm"
      >
        <span className="min-w-0 flex-1 truncate">{row.label}</span>
        {kindWord && <span className="text-xs font-normal text-muted-foreground">{kindWord}</span>}
        <Count count={row.unreadCount} />
      </button>
    </div>
  );
}

/**
 * The conversation rail (#4129): every conversation the current character is
 * in, on the far left, one selected at a time. **All** is the whole feed; a
 * row shows that conversation alone and addresses the composer to it. « folds
 * the rail to a strip of counts; the find box at the foot narrows the feed to
 * lines containing the text.
 */
export function ConversationRail({
  accountId,
  groups,
  selectedKey,
  onSelect,
  personActions,
  find,
  onFindChange,
}: ConversationRailProps) {
  const { preferences, update } = usePlayPreferences(accountId);
  const collapsed = preferences.railCollapsed;
  const rootRef = useRef<HTMLElement>(null);
  const [personMenu, setPersonMenu] = useState<PersonMenuState | null>(null);
  const openPersonMenu = (event: ReactMouseEvent<HTMLElement>, person: ThreadPersona) => {
    event.preventDefault();
    const rect = rootRef.current?.getBoundingClientRect();
    setPersonMenu({
      at: { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) },
      person,
    });
  };
  const totalUnread = allRailRows(groups).reduce((sum, row) => sum + row.unreadCount, 0);

  if (collapsed) {
    const counted = allRailRows(groups).filter((row) => row.unreadCount > 0);
    return (
      <aside
        ref={rootRef}
        className="flex h-full min-h-0 w-full flex-col items-center gap-2 py-2"
        aria-label="Conversations"
        data-testid="conversation-rail"
        data-collapsed="true"
      >
        <button
          type="button"
          aria-label="Expand the rail"
          title="Expand"
          className="rounded px-1.5 py-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={() => update({ railCollapsed: false })}
        >
          <ChevronsLeft className="h-4 w-4 rotate-180" aria-hidden="true" />
        </button>
        <div className="flex flex-col items-center gap-2" data-testid="rail-strip">
          {counted.map((row) => (
            <button
              key={row.key}
              type="button"
              className="rounded-full"
              onClick={() => {
                update({ railCollapsed: false });
                onSelect(row.key);
              }}
            >
              <Count count={row.unreadCount} label={row.label} />
            </button>
          ))}
        </div>
      </aside>
    );
  }

  const group = (label: string, rows: RailRow[], testId: string) =>
    rows.length > 0 && (
      <section className="mt-2" aria-label={label} data-testid={testId}>
        <h3 className="px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
          {label}
        </h3>
        {rows.map((row) => (
          <Row
            key={row.key}
            row={row}
            selected={selectedKey === row.key}
            onSelect={() => onSelect(row.key)}
            onPersonMenu={openPersonMenu}
          />
        ))}
      </section>
    );

  return (
    <aside
      ref={rootRef}
      className="relative flex h-full min-h-0 w-full flex-col"
      aria-label="Conversations"
      data-testid="conversation-rail"
    >
      <div className="flex shrink-0 items-center justify-between py-2 pl-3 pr-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Conversations
        </h2>
        <button
          type="button"
          aria-label="Collapse the rail"
          title="Collapse"
          className="rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={() => update({ railCollapsed: true })}
        >
          <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-1.5 pb-2">
        <div
          className={cn(
            'flex items-center gap-2 rounded-md px-2 hover:bg-muted',
            selectedKey === null && 'bg-accent font-semibold'
          )}
          data-testid="rail-row"
          data-rail-key="all"
        >
          <button
            type="button"
            aria-current={selectedKey === null ? 'true' : undefined}
            onClick={() => onSelect(null)}
            className="flex min-h-9 min-w-0 flex-1 items-center gap-2 py-1 text-left text-sm"
          >
            <span className="min-w-0 flex-1 truncate">All</span>
            {selectedKey !== null && <Count count={totalUnread} />}
          </button>
        </div>
        {group('Here', groups.here, 'rail-here')}
        {group('OOC Pages', groups.pages, 'rail-pages')}
      </div>
      <div className="shrink-0 border-t p-2">
        <Input
          type="search"
          value={find}
          onChange={(event) => onFindChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              onFindChange('');
            }
          }}
          placeholder="Find in this session"
          aria-label="Find in this session"
          autoComplete="off"
          className="h-8"
          data-testid="feed-find"
        />
      </div>
      <RailPersonMenu
        state={personMenu}
        onClose={() => setPersonMenu(null)}
        actions={personActions}
      />
    </aside>
  );
}
