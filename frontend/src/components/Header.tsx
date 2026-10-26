import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';
import { ModeToggle } from './ModeToggle';
import { SelectedCharacterChip } from './SelectedCharacterChip';
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuTrigger,
  NavigationMenuContent,
} from './ui/navigation-menu';
import { Sheet, SheetTrigger, SheetContent } from './ui/sheet';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { navigationMenuTriggerStyle } from '@/components/ui/navigation-menu-trigger-style';
import { useAppSelector } from '@/store/hooks';
import { useOpenSubmissionCount } from '@/staff/queries';
import { useGMAttention } from '@/gm/queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';

/** How often a tab without a socket re-reads the server's presence (#4321). */
const PRESENCE_REFETCH_MS = 30_000;
import { UnreadNarrativeBadge } from '@/narrative/components/UnreadNarrativeBadge';
import { UnreadMailBadge } from '@/mail/components/UnreadMailBadge';
import { useRitualSessionInbox } from '@/rituals/queries';
import { NO_DESCRIPTION } from '@/components/ui/dialog';

/**
 * Who sees a row (#4188): nothing for everyone, `auth` for any account, `gm`
 * for an account holding a GMProfile (assistant GMs hold one too, so this is
 * the whole GM gate), `staff` for `is_staff`.
 */
type NavRequirement = 'auth' | 'gm' | 'staff';

interface NavLink {
  to: string;
  label: string;
  requires?: NavRequirement;
  /** Rows sharing a section render under its label, after the unsectioned rows. */
  section?: string;
}

interface NavDropdown {
  type: 'dropdown';
  label: string;
  children: NavLink[];
  /** Which count the trigger's badge shows, when the group carries one. */
  badge?: 'gm-attention';
}

interface Viewer {
  account: boolean;
  isGM: boolean;
  isStaff: boolean;
}

function canSee(link: NavLink, viewer: Viewer): boolean {
  switch (link.requires) {
    case undefined:
      return true;
    case 'auth':
      return viewer.account;
    case 'gm':
      return viewer.isGM;
    case 'staff':
      return viewer.isStaff;
  }
}

/** The visible rows, unsectioned first, then each section's rows in first-seen order. */
function sectioned(links: NavLink[]): { section: string | undefined; rows: NavLink[] }[] {
  const groups = new Map<string | undefined, NavLink[]>();
  groups.set(undefined, []);
  for (const link of links) {
    const rows = groups.get(link.section);
    if (rows) rows.push(link);
    else groups.set(link.section, [link]);
  }
  return [...groups.entries()]
    .filter(([, rows]) => rows.length > 0)
    .map(([section, rows]) => ({ section, rows }));
}

/** Dropdown groups for secondary navigation links. */
const dropdownGroups: NavDropdown[] = [
  {
    type: 'dropdown',
    label: 'Characters',
    children: [
      { to: '/roster', label: 'Roster' },
      { to: '/magic/progression', label: 'Progression' },
      { to: '/threads', label: 'Threads' },
    ],
  },
  {
    type: 'dropdown',
    label: 'Story',
    children: [
      { to: '/scenes', label: 'Scenes' },
      { to: '/events', label: 'Events' },
      { to: '/stories/my-active', label: 'My Stories', requires: 'auth' },
      { to: '/books', label: 'Books', requires: 'auth' },
    ],
  },
  // #4188: story design and tracking. What waits on a GM lives on the
  // Dashboard's "Waiting on you" strip, not here (ADR-4188); the trigger
  // carries one count of all of it.
  {
    type: 'dropdown',
    label: 'GMing',
    badge: 'gm-attention',
    children: [
      { to: '/gm/dashboard', label: 'Dashboard', requires: 'gm' },
      { to: '/gm/story-builder', label: 'Story Builder', requires: 'gm' },
      { to: '/tables', label: 'Tables', requires: 'gm' },
      { to: '/stories/gm-queue', label: 'Lead GM Queue', requires: 'gm' },
      {
        to: '/stories/staff-workload',
        label: 'Story Workload',
        requires: 'staff',
        section: 'Staff',
      },
    ],
  },
  {
    type: 'dropdown',
    label: 'World',
    children: [
      { to: '/codex', label: 'Codex' },
      { to: '/tidings', label: 'Tidings' },
      { to: '/journals', label: 'Journals' },
      { to: '/realms', label: 'Realms' },
    ],
  },
];

export function Header() {
  const account = useAppSelector((state) => state.auth.account);
  const isStaff = account?.is_staff ?? false;
  const isGM = account?.is_gm ?? false;
  const viewer: Viewer = { account: account !== null, isGM, isStaff };
  const { data: pendingCount } = useOpenSubmissionCount(isStaff);
  const { data: attention } = useGMAttention(isGM);
  const badgeCounts: Record<NonNullable<NavDropdown['badge']>, number> = {
    'gm-attention': attention?.total ?? 0,
  };
  const { data: inboxSessions } = useRitualSessionInbox();
  const pendingInvitationCount = account ? (inboxSessions?.length ?? 0) : 0;

  // Docked-portrait chip (#3412): the app-wide surface for the account's
  // durable server-side character selection. `gameSlice.active` (not
  // `account.selected_entry` directly) is the source of truth here — it's
  // the same pointer GameTopBar/GamePage already key off, so the chip stays
  // in lockstep with a local session switch instead of lagging behind the
  // account refetch `useSelectCharacterMutation` triggers. Absent when
  // there's no selection: no empty chip, no placeholder slot — the header
  // renders exactly as it did before this existed.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  // #4321: the chip states presence from the server's `session_count` when
  // this tab holds no socket, so while a chip is up the list is refetched at
  // the presence panel's own cadence; a tab's own socket updates it at once.
  const { data: characters } = useMyRosterEntriesQuery(
    activeCharacterName ? { refetchInterval: PRESENCE_REFETCH_MS } : true
  );
  const selectedEntry = characters?.find((c) => c.name === activeCharacterName) ?? null;

  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <SiteTitle />
        {selectedEntry && <SelectedCharacterChip entry={selectedEntry} />}
        <NavigationMenu className="hidden md:block">
          <NavigationMenuList>
            <NavigationMenuItem>
              <Link to="/game" className={navigationMenuTriggerStyle()}>
                Play
              </Link>
            </NavigationMenuItem>
            {dropdownGroups.map((group) => {
              const visibleChildren = group.children.filter((child) => canSee(child, viewer));
              if (visibleChildren.length === 0) return null;
              const count = group.badge ? badgeCounts[group.badge] : 0;
              return (
                <NavigationMenuItem key={group.label}>
                  <NavigationMenuTrigger>
                    {group.label}
                    {count > 0 ? (
                      <Badge
                        variant="destructive"
                        className="ml-1.5 h-5 min-w-5 px-1 text-xs"
                        data-testid={`${group.badge}-badge`}
                      >
                        {count}
                      </Badge>
                    ) : null}
                  </NavigationMenuTrigger>
                  <NavigationMenuContent>
                    <ul className="flex flex-col gap-1 p-2">
                      {sectioned(visibleChildren).map(({ section, rows }) => (
                        <li
                          key={section ?? ''}
                          className={
                            section
                              ? 'mt-1 flex flex-col gap-1 border-t pt-2'
                              : 'flex flex-col gap-1'
                          }
                        >
                          {section ? (
                            <p className="px-3 text-xs font-semibold text-muted-foreground">
                              {section}
                            </p>
                          ) : null}
                          <ul className="flex flex-col gap-1">
                            {rows.map((child) => (
                              <li key={child.to}>
                                <Link to={child.to} className={navigationMenuTriggerStyle()}>
                                  {child.label}
                                </Link>
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </NavigationMenuContent>
                </NavigationMenuItem>
              );
            })}
            {account && (
              <NavigationMenuItem>
                <Link to="/rituals/sessions/inbox" className={navigationMenuTriggerStyle()}>
                  Inbox
                  {pendingInvitationCount > 0 ? (
                    <Badge
                      variant="destructive"
                      className="ml-1.5 h-5 min-w-5 px-1 text-xs"
                      data-testid="inbox-badge"
                    >
                      {pendingInvitationCount}
                    </Badge>
                  ) : null}
                </Link>
              </NavigationMenuItem>
            )}
            {isStaff && (
              <NavigationMenuItem>
                <Link to="/staff" className={navigationMenuTriggerStyle()}>
                  Staff
                  {pendingCount && pendingCount > 0 ? (
                    <Badge variant="destructive" className="ml-1.5 h-5 min-w-5 px-1 text-xs">
                      {pendingCount}
                    </Badge>
                  ) : null}
                </Link>
              </NavigationMenuItem>
            )}
            <NavigationMenuItem>
              <ModeToggle />
            </NavigationMenuItem>
            <NavigationMenuItem>
              <UnreadNarrativeBadge />
            </NavigationMenuItem>
            <NavigationMenuItem>
              <UnreadMailBadge />
            </NavigationMenuItem>
            <NavigationMenuItem>
              <UserNav />
            </NavigationMenuItem>
          </NavigationMenuList>
        </NavigationMenu>
        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Open menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent {...NO_DESCRIPTION} side="left" className="p-4">
              <nav className="flex flex-col gap-4">
                <Link to="/game" className="text-lg">
                  Play
                </Link>
                {dropdownGroups.map((group) => {
                  const visibleChildren = group.children.filter((child) => canSee(child, viewer));
                  if (visibleChildren.length === 0) return null;
                  const count = group.badge ? badgeCounts[group.badge] : 0;
                  return (
                    <div key={group.label} className="space-y-2">
                      <p className="text-sm font-semibold text-muted-foreground">
                        {group.label} {count > 0 ? `(${count})` : ''}
                      </p>
                      {sectioned(visibleChildren).map(({ section, rows }) => (
                        <div
                          key={section ?? ''}
                          className={
                            section
                              ? 'mt-1 flex flex-col gap-2 border-t pl-2 pt-2'
                              : 'flex flex-col gap-2 pl-2'
                          }
                        >
                          {section ? (
                            <p className="text-xs font-semibold text-muted-foreground">{section}</p>
                          ) : null}
                          {rows.map((child) => (
                            <Link key={child.to} to={child.to} className="text-lg">
                              {child.label}
                            </Link>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                })}
                {account && (
                  <Link to="/rituals/sessions/inbox" className="text-lg">
                    Inbox {pendingInvitationCount > 0 ? `(${pendingInvitationCount})` : ''}
                  </Link>
                )}
                {isStaff && (
                  <Link to="/staff" className="text-lg">
                    Staff {pendingCount && pendingCount > 0 ? `(${pendingCount})` : ''}
                  </Link>
                )}
                <ModeToggle />
                <UnreadNarrativeBadge />
                <UnreadMailBadge />
                <UserNav />
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
