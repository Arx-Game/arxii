import { useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useSystemErrorDetail, useUpdateSystemErrorStatus } from '@/staff/queries';

export function StaffSystemErrorDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const reportId = id ? parseInt(id, 10) : undefined;
  const { data: report, isLoading } = useSystemErrorDetail(reportId);
  const updateStatus = useUpdateSystemErrorStatus();

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!report) return <p className="p-8 text-muted-foreground">System error not found.</p>;

  function handleStatusChange(status: 'reviewed' | 'dismissed') {
    if (!reportId) return;
    updateStatus.mutate(
      { id: reportId, status },
      { onSuccess: () => navigate('/staff/system-errors') }
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">System Error Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-2">
            <span className="font-mono">{report.exception_type}</span>
            <div className="flex items-center gap-2">
              {report.occurrence_count > 1 && (
                <Badge variant="secondary">&times;{report.occurrence_count}</Badge>
              )}
              <Badge>{report.status}</Badge>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Where</p>
            <p>{report.label}</p>
          </div>
          {report.message && (
            <div>
              <p className="text-sm font-medium text-muted-foreground">Message</p>
              <p className="whitespace-pre-wrap">{report.message}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-muted-foreground">First seen</p>
              <p>{new Date(report.first_seen).toLocaleString()}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Last seen</p>
              <p>{new Date(report.last_seen).toLocaleString()}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Acting persona</p>
              <p>{report.actor_persona_name ?? '—'}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Signature</p>
              <p className="truncate font-mono text-xs">{report.signature}</p>
            </div>
          </div>
          <div>
            <p className="mb-1 text-sm font-medium text-muted-foreground">Traceback</p>
            <pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 font-mono text-xs leading-relaxed">
              {report.traceback}
            </pre>
          </div>
        </CardContent>
      </Card>

      {report.status === 'open' && (
        <div className="flex gap-2">
          <Button disabled={updateStatus.isPending} onClick={() => handleStatusChange('reviewed')}>
            Mark Reviewed
          </Button>
          <Button
            variant="outline"
            disabled={updateStatus.isPending}
            onClick={() => handleStatusChange('dismissed')}
          >
            Dismiss
          </Button>
        </div>
      )}
    </div>
  );
}
