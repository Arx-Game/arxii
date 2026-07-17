import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';
import { ModeToggle } from './ModeToggle';
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuTrigger,
  NavigationMenuContent,
  NavigationMenuViewport,
} from './ui/navigation-menu';
import { Sheet, SheetTrigger, SheetContent } from './ui/sheet';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { navigationMenuTriggerStyle } from '@/components/ui/navigation-menu-trigger-style';
import { useAppSelector } from '@/store/hooks';
import { useOpenSubmissionCount } from '@/staff/queries';
import { UnreadNarrativeBadge } from '@/narrative/components/UnreadNarrativeBadge';
import { UnreadMailBadge } from '@/mail/components/UnreadMailBadge';
import { useRitualSessionInbox } from '@/rituals/queries';

interface NavLink {
  to: string;
  label: string;
  authOnly?: boolean;
}

interface NavDropdown {
  type: 'dropdown';
  label: string;
  children: NavLink[];
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
      { to: '/stories/my-active', label: 'My Stories', authOnly: true },
      { to: '/books', label: 'Books', authOnly: true },
    ],
  },
  {
    type: 'dropdown',
    label: 'World',
    children: [
      { to: '/crossover/inbox', label: 'Crossover' },
      { to: '/codex', label: 'Codex' },
      { to: '/tidings', label: 'Tidings' },
    ],
  },
];

export function Header() {
  const account = useAppSelector((state) => state.auth.account);
  const isStaff = account?.is_staff ?? false;
  const { data: pendingCount } = useOpenSubmissionCount(isStaff);
  const { data: inboxSessions } = useRitualSessionInbox();
  const pendingInvitationCount = account ? (inboxSessions?.length ?? 0) : 0;

  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <SiteTitle />
        <NavigationMenu className="hidden md:block">
          <NavigationMenuList>
            <NavigationMenuItem>
              <Link to="/game" className={navigationMenuTriggerStyle()}>
                Play
              </Link>
            </NavigationMenuItem>
            {dropdownGroups.map((group) => {
              const visibleChildren = group.children.filter((child) => !child.authOnly || account);
              if (visibleChildren.length === 0) return null;
              return (
                <NavigationMenuItem key={group.label}>
                  <NavigationMenuTrigger>{group.label}</NavigationMenuTrigger>
                  <NavigationMenuContent>
                    <ul className="flex flex-col gap-1 p-2">
                      {visibleChildren.map((child) => (
                        <li key={child.to}>
                          <Link to={child.to} className={navigationMenuTriggerStyle()}>
                            {child.label}
                          </Link>
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
            {isStaff && (
              <NavigationMenuItem>
                <Link to="/stories/staff-workload" className={navigationMenuTriggerStyle()}>
                  Story Workload
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
          <NavigationMenuViewport />
        </NavigationMenu>
        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Open menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="p-4">
              <nav className="flex flex-col gap-4">
                <Link to="/game" className="text-lg">
                  Play
                </Link>
                {dropdownGroups.map((group) => {
                  const visibleChildren = group.children.filter(
                    (child) => !child.authOnly || account
                  );
                  if (visibleChildren.length === 0) return null;
                  return (
                    <div key={group.label} className="space-y-2">
                      <p className="text-sm font-semibold text-muted-foreground">{group.label}</p>
                      <div className="flex flex-col gap-2 pl-2">
                        {visibleChildren.map((child) => (
                          <Link key={child.to} to={child.to} className="text-lg">
                            {child.label}
                          </Link>
                        ))}
                      </div>
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
                {isStaff && (
                  <Link to="/stories/staff-workload" className="text-lg">
                    Story Workload
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
