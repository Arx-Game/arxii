import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { usePlayerReportList } from '@/staff/queries';
import type { SubmissionStatus } from '@/staff/types';
import { STATUS_OPTIONS, statusVariant } from '@/staff/utils';

export function StaffPlayerReportsPage() {
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | undefined>(undefined);
  const [page, setPage] = useState(1);
  const { data, isLoading } = usePlayerReportList(statusFilter, page);
  const items = data?.results;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Player Reports</h1>

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
      ) : !items?.length ? (
        <p className="text-muted-foreground">No player reports found.</p>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} to={`/staff/player-reports/${item.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">
                        {item.behavior_description.length > 80
                          ? item.behavior_description.slice(0, 80) + '...'
                          : item.behavior_description}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Reported: {item.reported_persona_name} ({item.reported_account_username})
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {item.reporter_persona_name} ({item.reporter_account_username}) &middot;{' '}
                        {new Date(item.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
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
