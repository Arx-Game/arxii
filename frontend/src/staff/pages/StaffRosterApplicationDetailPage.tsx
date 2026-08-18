import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useReviewRosterApplication, useRosterApplicationDetail } from '@/staff/queries';

interface InfoRowProps {
  label: string;
  value: string;
}

function InfoRow({ label, value }: Readonly<InfoRowProps>) {
  return (
    <div className="flex gap-2">
      <span className="min-w-32 font-medium text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function formatPolicyLabel(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatPolicyValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function StaffRosterApplicationDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const appId = id ? Number.parseInt(id, 10) : undefined;
  const { data: application, isLoading, isError } = useRosterApplicationDetail(appId);
  const review = useReviewRosterApplication();

  const [reviewNotes, setReviewNotes] = useState('');
  const [denyNotesMissing, setDenyNotesMissing] = useState(false);

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (isError) return <p className="p-8 text-muted-foreground">Failed to load application.</p>;
  if (!application) {
    return <p className="p-8 text-muted-foreground">Roster application not found.</p>;
  }

  const isPending = application.status === 'pending';

  function handleApprove() {
    if (!appId) return;
    setDenyNotesMissing(false);
    review.mutate(
      { id: appId, action: 'approve', reviewNotes },
      { onSuccess: () => navigate('/staff/roster-applications') }
    );
  }

  function handleDeny() {
    if (!appId) return;
    if (!reviewNotes.trim()) {
      setDenyNotesMissing(true);
      return;
    }
    setDenyNotesMissing(false);
    review.mutate(
      { id: appId, action: 'deny', reviewNotes },
      { onSuccess: () => navigate('/staff/roster-applications') }
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Roster Application Review</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>{application.character_name}</span>
            <Badge>{application.status_display}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <InfoRow label="Applicant" value={application.player_username} />
          <InfoRow label="Applied" value={new Date(application.applied_date).toLocaleString()} />
          <div>
            <p className="font-medium text-muted-foreground">Application</p>
            <p className="whitespace-pre-wrap">{application.application_text}</p>
          </div>
        </CardContent>
      </Card>

      {application.policy_review_info && (
        <Card>
          <CardHeader>
            <CardTitle>Policy Review</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              {Object.entries(application.policy_review_info).map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <dt className="min-w-32 font-medium text-muted-foreground">
                    {formatPolicyLabel(key)}
                  </dt>
                  <dd>{formatPolicyValue(value)}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      )}

      {isPending ? (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={reviewNotes}
              onChange={(e) => setReviewNotes(e.target.value)}
              placeholder="Notes for the applicant (required to deny)..."
              className="min-h-[100px]"
              disabled={review.isPending}
            />
            <div className="flex flex-wrap gap-2">
              <Button disabled={review.isPending} onClick={handleApprove}>
                Approve
              </Button>
              <Button variant="destructive" disabled={review.isPending} onClick={handleDeny}>
                Deny
              </Button>
            </div>
            {denyNotesMissing && (
              <p className="text-sm text-destructive">Notes are required to deny an application.</p>
            )}
            {review.isError && (
              <p className="text-sm text-destructive">
                {review.error instanceof Error
                  ? review.error.message
                  : 'Something went wrong. Try again.'}
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        (application.review_notes || application.reviewed_date) && (
          <Card>
            <CardHeader>
              <CardTitle>Review Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {application.reviewed_date && (
                <InfoRow
                  label="Reviewed"
                  value={new Date(application.reviewed_date).toLocaleString()}
                />
              )}
              {application.review_notes && (
                <p className="whitespace-pre-wrap">{application.review_notes}</p>
              )}
            </CardContent>
          </Card>
        )
      )}
    </div>
  );
}
