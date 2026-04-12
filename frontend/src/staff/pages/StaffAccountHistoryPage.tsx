import { Link, useParams } from 'react-router-dom';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAccountHistory } from '@/staff/queries';
import type { AccountHistoryCategory } from '@/staff/types';
import { detailPath } from '@/staff/utils';

function HistorySection({ title, category }: { title: string; category: AccountHistoryCategory }) {
  if (category.total === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          {title} ({category.total}
          {category.truncated ? '+' : ''})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {category.items.map((item) => (
          <Link
            key={`${item.source_type}-${item.source_pk}`}
            to={detailPath(item)}
            className="block rounded-md p-2 transition-colors hover:bg-muted/50"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{item.title}</p>
              <span className="text-xs text-muted-foreground">{item.status}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {new Date(item.created_at).toLocaleDateString()}
            </p>
          </Link>
        ))}
        {category.truncated && (
          <p className="text-xs text-muted-foreground">
            Showing first {category.items.length} of {category.total} items.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function StaffAccountHistoryPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = id ? parseInt(id, 10) : undefined;
  const { data: history, isLoading } = useAccountHistory(accountId);

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!history) return <p className="p-8 text-muted-foreground">Account not found.</p>;

  const totalItems =
    history.reports_against.total +
    history.reports_submitted.total +
    history.feedback.total +
    history.bug_reports.total +
    history.character_applications.total;

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Account History</h1>

      {totalItems === 0 ? (
        <p className="text-muted-foreground">No submission history for this account.</p>
      ) : (
        <>
          <HistorySection title="Reports Against" category={history.reports_against} />
          <HistorySection title="Reports Submitted" category={history.reports_submitted} />
          <HistorySection title="Feedback" category={history.feedback} />
          <HistorySection title="Bug Reports" category={history.bug_reports} />
          <HistorySection
            title="Character Applications"
            category={history.character_applications}
          />
        </>
      )}
    </div>
  );
}
