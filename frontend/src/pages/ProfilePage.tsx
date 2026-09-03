import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Link, Outlet, useLocation } from 'react-router-dom';

export function ProfilePage() {
  const { pathname } = useLocation();

  const getCurrentTab = () => {
    if (pathname.includes('/media')) return 'media';
    if (pathname.includes('/account')) return 'account';
    if (pathname.includes('/settings')) return 'settings';
    if (pathname.includes('/privacy')) return 'privacy';
    if (pathname.includes('/boundaries')) return 'boundaries';
    if (pathname.includes('/blocks')) return 'blocks';
    if (pathname.includes('/mutes')) return 'mutes';
    return 'mail';
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Tabs value={getCurrentTab()} className="w-full">
        <TabsList>
          <TabsTrigger value="mail" asChild>
            <Link to="/profile/mail">Mail</Link>
          </TabsTrigger>
          <TabsTrigger value="media" asChild>
            <Link to="/profile/media">Media</Link>
          </TabsTrigger>
          <TabsTrigger value="settings" asChild>
            <Link to="/profile/settings">Settings</Link>
          </TabsTrigger>
          <TabsTrigger value="account" asChild>
            <Link to="/profile/account">Account</Link>
          </TabsTrigger>
          <TabsTrigger value="privacy" asChild>
            <Link to="/profile/privacy">Privacy</Link>
          </TabsTrigger>
          <TabsTrigger value="boundaries" asChild>
            <Link to="/profile/boundaries">Boundaries</Link>
          </TabsTrigger>
          <TabsTrigger value="blocks" asChild>
            <Link to="/profile/blocks">Blocked</Link>
          </TabsTrigger>
          <TabsTrigger value="mutes" asChild>
            <Link to="/profile/mutes">Muted</Link>
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <Outlet />
    </div>
  );
}
