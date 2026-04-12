import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { usePlayerReportDetail, useUpdatePlayerReportStatus } from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';

export function StaffPlayerReportDetailPage() {
  const account = useAppSelector((state) => state.auth.account);
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const reportId = id ? parseInt(id, 10) : undefined;
  const { data: report, isLoading } = usePlayerReportDetail(reportId);
  const updateStatus = useUpdatePlayerReportStatus();

  if (!account?.is_staff) return <Navigate to="/" replace />;
  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!report) return <p className="p-8 text-muted-foreground">Report not found.</p>;

  function handleStatusChange(status: 'reviewed' | 'dismissed') {
    if (!reportId) return;
    updateStatus.mutate(
      { id: reportId, status },
      { onSuccess: () => navigate('/staff/player-reports') }
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Player Report Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Player Report #{report.id}</span>
            <Badge>{report.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Reported Player</p>
            <p>
              {report.reported_persona_name} ({report.reported_account_username}){' \u2014 '}
              <Link
                to={`/staff/accounts/${report.reported_account}/history`}
                className="text-primary underline"
              >
                View Account History
              </Link>
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Behavior Description</p>
            <p className="whitespace-pre-wrap">{report.behavior_description}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-muted-foreground">Reporter</p>
              <p>
                {report.reporter_persona_name} ({report.reporter_account_username})
              </p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Submitted</p>
              <p>{new Date(report.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Asked to Stop</p>
              <p>{report.asked_to_stop ? 'Yes' : 'No'}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Blocked or Muted</p>
              <p>{report.blocked_or_muted ? 'Yes' : 'No'}</p>
            </div>
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
