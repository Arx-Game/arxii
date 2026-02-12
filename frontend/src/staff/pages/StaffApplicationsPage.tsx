import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { statusLabel, statusVariant } from '@/character-creation/utils';
import { useApplications } from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';

const STATUS_OPTIONS: { label: string; value: string | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Submitted', value: 'submitted' },
  { label: 'In Review', value: 'in_review' },
  { label: 'Revisions Requested', value: 'revisions_requested' },
  { label: 'Approved', value: 'approved' },
  { label: 'Denied', value: 'denied' },
  { label: 'Withdrawn', value: 'withdrawn' },
];

export function StaffApplicationsPage() {
  const account = useAppSelector((state) => state.auth.account);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const { data, isLoading } = useApplications(statusFilter);
  const applications = data?.results;

  if (!account?.is_staff) return <Navigate to="/" replace />;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Character Applications</h1>

      {/* Status filter tabs */}
      <div className="mb-6 flex flex-wrap gap-2">
        {STATUS_OPTIONS.map((opt) => (
          <Button
            key={opt.label}
            variant={statusFilter === opt.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {/* Applications list */}
      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !applications?.length ? (
        <p className="text-muted-foreground">No applications found.</p>
      ) : (
        <div className="space-y-3">
          {applications.map((app) => (
            <Link key={app.id} to={`/staff/applications/${app.id}`}>
              <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                <CardContent className="flex items-center justify-between py-4">
                  <div>
                    <p className="font-medium">{app.draft_name}</p>
                    <p className="text-sm text-muted-foreground">
                      by {app.player_name} &middot;{' '}
                      {new Date(app.submitted_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {app.reviewer_name && (
                      <span className="text-xs text-muted-foreground">{app.reviewer_name}</span>
                    )}
                    <Badge variant={statusVariant(app.status)}>{statusLabel(app.status)}</Badge>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
