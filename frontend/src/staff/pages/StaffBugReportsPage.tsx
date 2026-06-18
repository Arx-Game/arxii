import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { NextPrevPagination, StatusFilterBar } from '@/staff/components/listControls';
import { useBugReportList } from '@/staff/queries';
import type { SubmissionStatus } from '@/staff/types';
import { STATUS_OPTIONS, statusVariant } from '@/staff/utils';

export function StaffBugReportsPage() {
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | undefined>(undefined);
  const [page, setPage] = useState(1);
  const { data, isLoading } = useBugReportList(statusFilter, page);
  const items = data?.results;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Bug Reports</h1>

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
        <p className="text-muted-foreground">No bug reports found.</p>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} to={`/staff/bug-reports/${item.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">
                        {item.description.length > 80
                          ? item.description.slice(0, 80) + '...'
                          : item.description}
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
