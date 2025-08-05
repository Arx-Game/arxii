import { SiteTitle } from './SiteTitle';
import { UserNav } from './UserNav';

export function Header() {
  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <SiteTitle />
        <UserNav />
      </div>
    </header>
  );
}
