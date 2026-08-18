import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { NextPrevPagination, StatusFilterBar } from '@/staff/components/listControls';
import { useGMApplicationList } from '@/staff/queries';
import type { GMApplicationStatus } from '@/staff/types';

const GM_STATUS_OPTIONS: { label: string; value: GMApplicationStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Denied', value: 'denied' },
  { label: 'Withdrawn', value: 'withdrawn' },
];

function gmStatusVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
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

export function StaffGMApplicationsPage() {
  const [statusFilter, setStatusFilter] = useState<GMApplicationStatus | undefined>(undefined);
  const [page, setPage] = useState(1);
  const { data, isLoading } = useGMApplicationList(statusFilter, page);
  const items = data?.results;

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">GM Applications</h1>

      <StatusFilterBar
        options={GM_STATUS_OPTIONS}
        value={statusFilter}
        onChange={(value) => {
          setStatusFilter(value);
          setPage(1);
        }}
      />

      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !items?.length ? (
        <p className="text-muted-foreground">No GM applications found.</p>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} to={`/staff/gm-applications/${item.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">
                        {item.application_text.length > 80
                          ? item.application_text.slice(0, 80) + '...'
                          : item.application_text}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {item.account_username} &middot;{' '}
                        {new Date(item.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant={gmStatusVariant(item.status)}>{item.status}</Badge>
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
