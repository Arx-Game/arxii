/**
 * RitualSessionDetailPage — full view of a single ritual session.
 *
 * Initiator view: shows Fire/Cancel controls + polling for live updates.
 * Participant view: read-only with a Respond button that opens the response dialog.
 *
 * The detail endpoint does not carry participant_fields schema. The response dialog
 * is passed the ritual's participant_fields from the ritual object (fetched via
 * useRitual when needed). For Slice B, we skip the participant_fields form in the
 * inline response and route them through the dialog props.
 *
 * Threshold logic (client-side derivation per spec):
 *   FORMATION  — all participants ACCEPTED, count ≥ 2
 *   INDUCTION  — more ACCEPTED than DECLINED, count ≥ 2
 *   BILATERAL  — exactly 2 ACCEPTED
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  useRitualSessionDetail,
  useFireRitualSession,
  useCancelRitualSession,
} from '@/rituals/queries';
import { RitualSessionResponseDialog } from '../components/RitualSessionResponseDialog';
import type { RitualSessionDetail } from '../api';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="space-y-4" data-testid="detail-skeleton">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Threshold derivation
// ---------------------------------------------------------------------------

function isThresholdMet(session: RitualSessionDetail): boolean {
  const { participants, participation_rule } = session;
  const accepted = participants.filter((p) => p.state === 'ACCEPTED').length;
  const declined = participants.filter((p) => p.state === 'DECLINED').length;
  const total = participants.length;

  switch (participation_rule) {
    case 'FORMATION':
      // All accepted, at least 2 participants
      return total >= 2 && accepted === total;
    case 'INDUCTION':
      // More accepted than declined, at least 2 participants total
      return total >= 2 && accepted > declined;
    case 'BILATERAL':
      // Exactly 2 accepted
      return accepted === 2;
    default:
      // Unknown rule: require all accepted with ≥ 2 (safe fallback)
      return total >= 2 && accepted === total;
  }
}

// ---------------------------------------------------------------------------
// State badge
// ---------------------------------------------------------------------------

const STATE_LABELS: Record<string, string> = {
  INVITED: 'Invited',
  ACCEPTED: 'Accepted',
  DECLINED: 'Declined',
};

const STATE_CLASSES: Record<string, string> = {
  INVITED: 'bg-yellow-100 text-yellow-800',
  ACCEPTED: 'bg-green-100 text-green-800',
  DECLINED: 'bg-red-100 text-red-800',
};

function StateBadge({ state }: { state: string }) {
  const label = STATE_LABELS[state] ?? state;
  const cls = STATE_CLASSES[state] ?? 'bg-muted text-muted-foreground';
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}

// ---------------------------------------------------------------------------
// Participant row
// ---------------------------------------------------------------------------

function ParticipantRow({ participant }: { participant: RitualSessionDetail['participants'][0] }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{participant.character_name}</span>
        <StateBadge state={participant.state} />
      </div>
      {participant.responded_at && (
        <span className="text-xs text-muted-foreground">
          {new Date(participant.responded_at).toLocaleDateString()}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page
// ---------------------------------------------------------------------------

interface DetailInnerProps {
  sessionId: number;
}

function RitualSessionDetailInner({ sessionId }: DetailInnerProps) {
  const navigate = useNavigate();
  const account = useSelector((state: RootState) => state.auth.account);

  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const characterSheetId = activeCharacter?.id ?? null;

  const [respondOpen, setRespondOpen] = useState(false);
  const [cancelConfirm, setCancelConfirm] = useState(false);

  const { data: session, isLoading, isError } = useRitualSessionDetail(sessionId);
  const fireMutation = useFireRitualSession();
  const cancelMutation = useCancelRitualSession();

  if (isLoading) return <DetailSkeleton />;

  if (isError || !session) {
    return (
      <p className="py-8 text-center text-destructive" data-testid="detail-error">
        Failed to load session. It may have expired or been cancelled.
      </p>
    );
  }

  // Determine the current user's role in this session
  const isInitiator = session.initiator_id === characterSheetId;
  const myParticipant = characterSheetId
    ? session.participants.find((p) => p.character_sheet_id === characterSheetId)
    : null;
  const canRespond =
    !isInitiator && myParticipant?.state === 'INVITED' && characterSheetId !== null;

  const thresholdMet = isThresholdMet(session);

  function handleFire() {
    fireMutation.mutate(sessionId, {
      onSuccess: () => {
        // Navigate to rituals list after fire (result_kind/result_id not exposed in
        // the list serializer response from useFireRitualSession — see queries.ts comment).
        navigate('/rituals');
      },
    });
  }

  function handleCancel() {
    cancelMutation.mutate(sessionId, {
      onSuccess: () => {
        navigate('/rituals/sessions/inbox');
      },
    });
  }

  const fireError = fireMutation.isError
    ? fireMutation.error instanceof Error
      ? fireMutation.error.message
      : 'Failed to fire session'
    : null;
  const cancelError = cancelMutation.isError
    ? cancelMutation.error instanceof Error
      ? cancelMutation.error.message
      : 'Failed to cancel session'
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" data-testid="session-ritual-name">
          {session.ritual_name}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Initiated by <span className="font-medium">{session.initiator_name}</span> ·{' '}
          {session.participation_rule}
        </p>
      </div>

      {/* Proposed terms */}
      {session.proposed_terms && (
        <div className="rounded-md bg-muted px-3 py-2 text-sm italic text-muted-foreground">
          {session.proposed_terms}
        </div>
      )}

      {/* Error banners */}
      {fireError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {fireError}
        </div>
      )}
      {cancelError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {cancelError}
        </div>
      )}

      {/* Participants */}
      <section>
        <h2 className="mb-2 text-lg font-semibold">Participants</h2>
        <div className="space-y-2" data-testid="participants-list">
          {session.participants.map((p) => (
            <ParticipantRow key={p.character_sheet_id} participant={p} />
          ))}
        </div>
        {/* Threshold status */}
        <p className="mt-2 text-sm text-muted-foreground">
          {thresholdMet ? (
            <span className="font-medium text-green-700">Threshold met — ready to fire.</span>
          ) : (
            <span>Waiting for participants to respond.</span>
          )}
        </p>
      </section>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        {isInitiator && (
          <>
            <Button
              onClick={handleFire}
              disabled={!thresholdMet || fireMutation.isPending}
              title={!thresholdMet ? 'Threshold not yet met' : undefined}
              data-testid="fire-button"
            >
              {fireMutation.isPending ? 'Firing…' : 'Fire Ritual'}
            </Button>

            {cancelConfirm ? (
              <div className="flex gap-2">
                <span className="self-center text-sm text-muted-foreground">
                  Cancel this session?
                </span>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleCancel}
                  disabled={cancelMutation.isPending}
                  data-testid="cancel-confirm-button"
                >
                  {cancelMutation.isPending ? 'Cancelling…' : 'Yes, cancel'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCancelConfirm(false)}
                  disabled={cancelMutation.isPending}
                >
                  Keep
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                onClick={() => setCancelConfirm(true)}
                data-testid="cancel-button"
              >
                Cancel Session
              </Button>
            )}
          </>
        )}

        {canRespond && characterSheetId !== null && (
          <>
            <Button onClick={() => setRespondOpen(true)} data-testid="respond-button">
              Respond
            </Button>
            <RitualSessionResponseDialog
              session={session}
              participantId={characterSheetId}
              open={respondOpen}
              onOpenChange={setRespondOpen}
              onSuccess={() => {
                setRespondOpen(false);
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function RitualSessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id ? Number(id) : 0;

  if (!sessionId || isNaN(sessionId)) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <p className="text-destructive">Invalid session ID.</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <RitualSessionDetailInner sessionId={sessionId} />
      </ErrorBoundary>
    </div>
  );
}
