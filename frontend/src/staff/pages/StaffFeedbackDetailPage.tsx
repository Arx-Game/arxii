import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useFeedbackDetail, useUpdateFeedbackStatus } from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';

export function StaffFeedbackDetailPage() {
  const account = useAppSelector((state) => state.auth.account);
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const feedbackId = id ? parseInt(id, 10) : undefined;
  const { data: feedback, isLoading } = useFeedbackDetail(feedbackId);
  const updateStatus = useUpdateFeedbackStatus();

  if (!account?.is_staff) return <Navigate to="/" replace />;
  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!feedback) return <p className="p-8 text-muted-foreground">Feedback not found.</p>;

  function handleStatusChange(status: 'reviewed' | 'dismissed') {
    if (!feedbackId) return;
    updateStatus.mutate(
      { id: feedbackId, status },
      { onSuccess: () => navigate('/staff/feedback') }
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Feedback Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Feedback #{feedback.id}</span>
            <Badge>{feedback.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Description</p>
            <p className="whitespace-pre-wrap">{feedback.description}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-muted-foreground">Reporter</p>
              <p>
                {feedback.reporter_persona_name} ({feedback.reporter_account_username})
              </p>
            </div>
            <div>
              <p className="font-medium text-muted-foreground">Submitted</p>
              <p>{new Date(feedback.created_at).toLocaleString()}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {feedback.status === 'open' && (
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
