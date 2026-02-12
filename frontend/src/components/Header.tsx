import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';
import { ModeToggle } from './ModeToggle';
import { NavigationMenu, NavigationMenuList, NavigationMenuItem } from './ui/navigation-menu';
import { Sheet, SheetTrigger, SheetContent } from './ui/sheet';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { navigationMenuTriggerStyle } from '@/components/ui/navigation-menu-trigger-style';
import { useAppSelector } from '@/store/hooks';
import { usePendingApplicationCount } from '@/staff/queries';

const links = [
  { to: '/game', label: 'Play' },
  { to: '/roster', label: 'Roster' },
  { to: '/scenes', label: 'Scenes' },
  { to: '/codex', label: 'Codex' },
  { to: '/news', label: 'News' },
  { to: '/community', label: 'Community' },
];

export function Header() {
  const account = useAppSelector((state) => state.auth.account);
  const isStaff = account?.is_staff ?? false;
  const pendingCountQuery = usePendingApplicationCount();
  const pendingCount = isStaff ? pendingCountQuery.data : undefined;

  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <SiteTitle />
        <NavigationMenu className="hidden md:block">
          <NavigationMenuList>
            {links.map((link) => (
              <NavigationMenuItem key={link.to}>
                <Link to={link.to} className={navigationMenuTriggerStyle()}>
                  {link.label}
                </Link>
              </NavigationMenuItem>
            ))}
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
            <SheetContent side="left" className="p-4">
              <nav className="flex flex-col gap-4">
                {links.map((link) => (
                  <Link key={link.to} to={link.to} className="text-lg">
                    {link.label}
                  </Link>
                ))}
                {isStaff && (
                  <Link to="/staff" className="text-lg">
                    Staff {pendingCount && pendingCount > 0 ? `(${pendingCount})` : ''}
                  </Link>
                )}
                <ModeToggle />
                <UserNav />
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
