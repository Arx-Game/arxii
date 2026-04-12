import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useGMApplicationDetail, useUpdateGMApplication } from '@/staff/queries';

const TERMINAL_STATUSES = ['approved', 'denied', 'withdrawn'];

export function StaffGMApplicationDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const appId = id ? parseInt(id, 10) : undefined;
  const { data: application, isLoading } = useGMApplicationDetail(appId);
  const update = useUpdateGMApplication();

  const [staffResponse, setStaffResponse] = useState('');

  useEffect(() => {
    if (application) {
      setStaffResponse(application.staff_response || '');
    }
  }, [application]);

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!application) return <p className="p-8 text-muted-foreground">GM application not found.</p>;

  const isTerminal = TERMINAL_STATUSES.includes(application.status);

  function handleApprove() {
    if (!appId) return;
    update.mutate(
      { id: appId, data: { status: 'approved', staff_response: staffResponse } },
      { onSuccess: () => navigate('/staff/gm-applications') }
    );
  }

  function handleDeny() {
    if (!appId) return;
    update.mutate(
      { id: appId, data: { status: 'denied', staff_response: staffResponse } },
      { onSuccess: () => navigate('/staff/gm-applications') }
    );
  }

  function handleSaveResponse() {
    if (!appId) return;
    update.mutate({ id: appId, data: { staff_response: staffResponse } });
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">GM Application Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Application #{application.id}</span>
            <Badge>{application.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Application Text</p>
            <p className="whitespace-pre-wrap">{application.application_text}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-muted-foreground">Applicant</p>
              <p>{application.account_username}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Submitted</p>
              <p>{new Date(application.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Updated</p>
              <p>{new Date(application.updated_at).toLocaleString()}</p>
            </div>
            {application.reviewed_by != null && (
              <div>
                <p className="font-medium text-muted-foreground">Reviewed By</p>
                <p>{application.reviewed_by_username ?? `Account #${application.reviewed_by}`}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Staff Response</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={staffResponse}
            onChange={(e) => setStaffResponse(e.target.value)}
            placeholder="Add a response to the applicant..."
            className="min-h-[120px]"
            disabled={isTerminal}
          />
          {!isTerminal && (
            <div className="flex flex-wrap gap-2">
              <Button disabled={update.isPending} onClick={handleApprove}>
                Approve
              </Button>
              <Button variant="destructive" disabled={update.isPending} onClick={handleDeny}>
                Deny
              </Button>
              <Button variant="outline" disabled={update.isPending} onClick={handleSaveResponse}>
                Save Response
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
