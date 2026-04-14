import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOpenSubmissionCount, usePendingApplicationCount } from '@/staff/queries';

export function StaffHubPage() {
  const { data: pendingAppCount } = usePendingApplicationCount();
  const { data: openInboxCount } = useOpenSubmissionCount();

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Staff Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <Link to="/staff/inbox">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Inbox
                {openInboxCount && openInboxCount > 0 ? (
                  <Badge variant="destructive">{openInboxCount}</Badge>
                ) : null}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Triage open submissions across all categories.
              </p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/staff/feedback">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle>Feedback</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Review player feedback and suggestions.
              </p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/staff/bug-reports">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle>Bug Reports</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Review and triage bug reports.</p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/staff/player-reports">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle>Player Reports</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Review reports of problematic player behavior.
              </p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/staff/gm-applications">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle>GM Applications</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Review player applications to become GMs.
              </p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/staff/applications">
          <Card className="cursor-pointer transition-colors hover:bg-muted/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Roster Applications
                {pendingAppCount && pendingAppCount > 0 ? (
                  <Badge variant="destructive">{pendingAppCount}</Badge>
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
      </div>
    </div>
  );
}
