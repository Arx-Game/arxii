import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Link, Outlet, useLocation } from 'react-router-dom';

export function ProfilePage() {
  const { pathname } = useLocation();
  const currentTab = pathname.includes('/media') ? 'media' : 'mail';

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Tabs value={currentTab} className="w-full">
        <TabsList>
          <TabsTrigger value="mail" asChild>
            <Link to="mail">Mail</Link>
          </TabsTrigger>
          <TabsTrigger value="media" asChild>
            <Link to="media">Media</Link>
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <Outlet />
    </div>
  );
}
