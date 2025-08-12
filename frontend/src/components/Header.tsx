import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';
import { ModeToggle } from './ModeToggle';
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  navigationMenuTriggerStyle,
} from './ui/navigation-menu';
import { Sheet, SheetTrigger, SheetContent } from './ui/sheet';
import { Button } from './ui/button';

const links = [
  { to: '/game', label: 'Play' },
  { to: '/roster', label: 'Roster' },
  { to: '/scenes', label: 'Scenes' },
  { to: '/news', label: 'News' },
  { to: '/community', label: 'Community' },
];

export function Header() {
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
