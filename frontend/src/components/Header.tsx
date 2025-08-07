import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';
import { ModeToggle } from './ModeToggle';

export function Header() {
  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <SiteTitle />
        <div className="flex items-center gap-4">
          <ModeToggle />
          <UserNav />
        </div>
      </div>
    </header>
  );
}
