import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Link, Outlet, useLocation } from 'react-router-dom';

export function ProfilePage() {
  const { pathname } = useLocation();

  const getCurrentTab = () => {
    if (pathname.includes('/media')) return 'media';
    if (pathname.includes('/settings')) return 'settings';
    return 'mail';
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Tabs value={getCurrentTab()} className="w-full">
        <TabsList>
          <TabsTrigger value="mail" asChild>
            <Link to="mail">Mail</Link>
          </TabsTrigger>
          <TabsTrigger value="media" asChild>
            <Link to="media">Media</Link>
          </TabsTrigger>
          <TabsTrigger value="settings" asChild>
            <Link to="settings">Settings</Link>
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <Outlet />
    </div>
  );
}
