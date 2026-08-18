import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useRosterApplications } from '@/staff/queries';
import type { RosterApplicationStatus } from '@/staff/types';

const STATUS_OPTIONS: { label: string; value: RosterApplicationStatus | undefined }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Denied', value: 'denied' },
  { label: 'Withdrawn', value: 'withdrawn' },
];

function rosterStatusVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  switch (status) {
    case 'pending':
      return 'default';
    case 'approved':
      return 'secondary';
    case 'denied':
      return 'destructive';
    case 'withdrawn':
      return 'outline';
    default:
      return 'outline';
  }
}

export function StaffRosterApplicationsPage() {
  const [statusFilter, setStatusFilter] = useState<RosterApplicationStatus | undefined>('pending');
  const [page, setPage] = useState(1);
  const { data, isLoading } = useRosterApplications(statusFilter, page);
  const applications = data?.results;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Roster Character Applications</h1>

      <div className="mb-6 flex flex-wrap gap-2">
        {STATUS_OPTIONS.map((opt) => (
          <Button
            key={opt.label}
            variant={statusFilter === opt.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              setStatusFilter(opt.value);
              setPage(1);
            }}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !applications?.length ? (
        <p className="text-muted-foreground">No roster applications found.</p>
      ) : (
        <>
          <div className="space-y-3">
            {applications.map((app) => (
              <Link key={app.id} to={`/staff/roster-applications/${app.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">{app.character_name}</p>
                      <p className="text-sm text-muted-foreground">
                        by {app.player_username} &middot;{' '}
                        {new Date(app.applied_date).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant={rosterStatusVariant(app.status)}>{app.status_display}</Badge>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>

          {data && data.count > 0 && (data.next || data.previous) && (
            <div className="mt-6 flex items-center justify-center gap-4">
              <Button
                variant="outline"
                size="sm"
                disabled={!data.previous}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">Page {page}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={!data.next}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
