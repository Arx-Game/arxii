import { useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ReportDetailActions } from '@/staff/components/ReportDetailActions';
import {
  useBugReportDetail,
  useFileBugReportIssue,
  useUpdateBugReportStatus,
} from '@/staff/queries';

export function StaffBugReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const reportId = id ? parseInt(id, 10) : undefined;
  const { data: report, isLoading } = useBugReportDetail(reportId);
  const updateStatus = useUpdateBugReportStatus();
  const fileIssue = useFileBugReportIssue();

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!report) return <p className="p-8 text-muted-foreground">Bug report not found.</p>;

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Bug Report Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Bug Report #{report.id}</span>
            <Badge>{report.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Description</p>
            <p className="whitespace-pre-wrap">{report.description}</p>
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
          </div>
        </CardContent>
      </Card>

      <ReportDetailActions
        report={report}
        updateStatus={updateStatus}
        fileIssue={fileIssue}
        listPath="/staff/bug-reports"
      />
    </div>
  );
}
