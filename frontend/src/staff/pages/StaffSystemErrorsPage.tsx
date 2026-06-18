import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { NextPrevPagination, StatusFilterBar } from '@/staff/components/listControls';
import { useSystemErrorList } from '@/staff/queries';
import type { SubmissionStatus } from '@/staff/types';
import { STATUS_OPTIONS, statusVariant } from '@/staff/utils';

export function StaffSystemErrorsPage() {
  // Default to OPEN — the triage queue, not the full archive.
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | undefined>('open');
  const [page, setPage] = useState(1);
  const { data, isLoading } = useSystemErrorList(statusFilter, page);
  const items = data?.results;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-2 text-2xl font-bold">System Errors</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Auto-captured runtime errors. Recurring faults are deduplicated into a single row with an
        occurrence count.
      </p>

      <StatusFilterBar
        options={STATUS_OPTIONS}
        value={statusFilter}
        onChange={(value) => {
          setStatusFilter(value);
          setPage(1);
        }}
      />

      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !items?.length ? (
        <p className="text-muted-foreground">No system errors found.</p>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} to={`/staff/system-errors/${item.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        <span className="font-mono">{item.exception_type}</span> in {item.label}
                      </p>
                      <p className="truncate text-sm text-muted-foreground">
                        {item.message || 'No message'} &middot; last seen{' '}
                        {new Date(item.last_seen).toLocaleString()}
                      </p>
                    </div>
                    <div className="ml-4 flex shrink-0 items-center gap-2">
                      {item.occurrence_count > 1 && (
                        <Badge variant="secondary">&times;{item.occurrence_count}</Badge>
                      )}
                      <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>

          <NextPrevPagination
            page={page}
            hasPrevious={!!data?.previous}
            hasNext={!!data?.next}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
