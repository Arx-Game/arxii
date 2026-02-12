import { useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { ApplicationThread } from '@/character-creation/components/ApplicationThread';
import type { ApplicationStatus } from '@/character-creation/types';
import {
  useAddStaffComment,
  useApplicationDetail,
  useApproveApplication,
  useClaimApplication,
  useDenyApplication,
  useRequestRevisions,
} from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';

function statusLabel(status: ApplicationStatus): string {
  const labels: Record<ApplicationStatus, string> = {
    submitted: 'Submitted',
    in_review: 'In Review',
    revisions_requested: 'Revisions Requested',
    approved: 'Approved',
    denied: 'Denied',
    withdrawn: 'Withdrawn',
  };
  return labels[status] ?? status;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="min-w-24 font-medium text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function StaffApplicationDetailPage() {
  const account = useAppSelector((state) => state.auth.account);
  const { id } = useParams<{ id: string }>();
  const appId = id ? parseInt(id, 10) : undefined;
  const { data: application, isLoading } = useApplicationDetail(appId);

  const claim = useClaimApplication();
  const approve = useApproveApplication();
  const requestRevisions = useRequestRevisions();
  const deny = useDenyApplication();
  const addComment = useAddStaffComment();

  const [actionComment, setActionComment] = useState('');

  if (!account?.is_staff) return <Navigate to="/" replace />;
  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!application) return <p className="p-8 text-muted-foreground">Application not found.</p>;

  const summary = application.draft_summary;
  const isTerminal = ['approved', 'denied', 'withdrawn'].includes(application.status);

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Application Review</h1>

      {/* Draft Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>{summary.first_name || 'Unnamed Character'}</span>
            <Badge>{statusLabel(application.status)}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {summary.species && <InfoRow label="Species" value={summary.species} />}
          {summary.area && <InfoRow label="Homeland" value={summary.area} />}
          {summary.beginnings && <InfoRow label="Beginnings" value={summary.beginnings} />}
          {summary.family && <InfoRow label="Family" value={summary.family} />}
          {summary.gender && <InfoRow label="Gender" value={summary.gender} />}
          {summary.age && <InfoRow label="Age" value={String(summary.age)} />}
          {summary.description && (
            <div>
              <p className="font-medium text-muted-foreground">Description</p>
              <p className="whitespace-pre-wrap">{summary.description}</p>
            </div>
          )}
          {summary.personality && (
            <div>
              <p className="font-medium text-muted-foreground">Personality</p>
              <p className="whitespace-pre-wrap">{summary.personality}</p>
            </div>
          )}
          {summary.background && (
            <div>
              <p className="font-medium text-muted-foreground">Background</p>
              <p className="whitespace-pre-wrap">{summary.background}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action buttons */}
      {!isTerminal && (
        <Card>
          <CardContent className="space-y-4 pt-4">
            <Textarea
              value={actionComment}
              onChange={(e) => setActionComment(e.target.value)}
              placeholder="Add a comment with your action..."
              className="min-h-[100px]"
            />
            <div className="flex flex-wrap gap-2">
              {application.status === 'submitted' && (
                <Button onClick={() => claim.mutate(application.id)}>Claim for Review</Button>
              )}
              {application.status === 'in_review' && (
                <>
                  <Button
                    onClick={() => {
                      approve.mutate({ id: application.id, comment: actionComment });
                      setActionComment('');
                    }}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      if (!actionComment.trim()) {
                        alert('Please provide feedback for the player.');
                        return;
                      }
                      requestRevisions.mutate({
                        id: application.id,
                        comment: actionComment,
                      });
                      setActionComment('');
                    }}
                  >
                    Request Revisions
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => {
                      if (!actionComment.trim()) {
                        alert('Please provide a reason for denial.');
                        return;
                      }
                      deny.mutate({ id: application.id, comment: actionComment });
                      setActionComment('');
                    }}
                  >
                    Deny
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Conversation thread */}
      <ApplicationThread
        application={application}
        onAddComment={(text) => addComment.mutate({ id: application.id, text })}
        isAddingComment={addComment.isPending}
        readOnly={isTerminal}
      />
    </div>
  );
}
