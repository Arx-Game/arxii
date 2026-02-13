import { Link, Navigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { usePendingApplicationCount } from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';

export function StaffHubPage() {
  const account = useAppSelector((state) => state.auth.account);
  const { data: pendingCount } = usePendingApplicationCount();

  if (!account?.is_staff) return <Navigate to="/" replace />;

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Staff Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <Link to="/staff/applications">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Applications
                {pendingCount && pendingCount > 0 ? (
                  <Badge variant="destructive">{pendingCount}</Badge>
                ) : null}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Review character creation submissions.
              </p>
            </CardContent>
          </Card>
        </Link>
        {/* Future sections will go here */}
      </div>
    </div>
  );
}
