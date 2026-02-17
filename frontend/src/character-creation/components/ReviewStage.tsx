/**
 * Stage 11: Review & Submit
 *
 * Final review of character sheet with validation summary.
 * Handles 4 application states:
 *   1. No application (building) - submit with notes
 *   2. Submitted / In Review (locked) - un-submit or withdraw
 *   3. Revisions Requested (editable) - resubmit or withdraw
 *   4. Denied / Withdrawn (read-only grace period)
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  Clock,
  ExternalLink,
  Info,
  MessageSquare,
  Send,
  Undo2,
  UserPlus,
  XCircle,
} from 'lucide-react';
import {
  useAddToRoster,
  useDraftApplication,
  useDraftCGPoints,
  useResubmitDraft,
  useSubmitDraft,
  useUnsubmitDraft,
  useWithdrawDraft,
} from '../queries';
import type { ApplicationStatus, CharacterDraft } from '../types';
import { Stage, STAGE_LABELS } from '../types';
import { statusLabel, statusVariant } from '../utils';

interface ReviewStageProps {
  draft: CharacterDraft;
  isStaff: boolean;
  onStageSelect: (stage: Stage) => void;
}

export function ReviewStage({ draft, isStaff, onStageSelect }: ReviewStageProps) {
  const submitDraft = useSubmitDraft();
  const addToRoster = useAddToRoster();
  const application = useDraftApplication(draft.id);
  const unsubmit = useUnsubmitDraft();
  const withdraw = useWithdrawDraft();
  const resubmit = useResubmitDraft();

  const cgPoints = useDraftCGPoints(draft.id);

  const [submissionNotes, setSubmissionNotes] = useState('');
  const [resubmitComment, setResubmitComment] = useState('');
  const [showConversionModal, setShowConversionModal] = useState(false);

  const stageCompletion = draft.stage_completion;
  const incompleteStages = Object.entries(stageCompletion)
    .filter(([stage, complete]) => !complete && parseInt(stage) !== Stage.REVIEW)
    .map(([stage]) => parseInt(stage) as Stage);

  const canSubmit = incompleteStages.length === 0;
  const draftData = draft.draft_data;
  const familyName =
    draft.family?.name ?? (draft.selected_beginnings?.family_known === false ? '' : '');
  const fullName = draftData.first_name
    ? familyName
      ? `${draftData.first_name} ${familyName}`
      : draftData.first_name
    : 'Unnamed Character';

  const appStatus = application.data?.status ?? null;
  const hasApplication = application.data != null;

  const cgRemaining = cgPoints.data?.remaining ?? draft.cg_points_remaining;
  const conversionRate = cgPoints.data?.xp_conversion_rate ?? 2;
  const bonusXP = cgRemaining * conversionRate;
  const hasUnspentPoints = cgRemaining > 0;

  const handleSubmit = () => {
    if (hasUnspentPoints) {
      setShowConversionModal(true);
      return;
    }
    submitDraft.mutate({ draftId: draft.id, submissionNotes });
  };

  const handleConfirmSubmit = () => {
    setShowConversionModal(false);
    submitDraft.mutate({ draftId: draft.id, submissionNotes });
  };

  const handleUnsubmit = () => {
    unsubmit.mutate(draft.id);
  };

  const handleWithdraw = () => {
    const confirmed = window.confirm(
      'Are you sure you want to withdraw this application? This cannot be undone.'
    );
    if (confirmed) {
      withdraw.mutate(draft.id);
    }
  };

  const handleResubmit = () => {
    resubmit.mutate({ draftId: draft.id, comment: resubmitComment || undefined });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">Review & Submit</h2>
        <p className="mt-2 text-muted-foreground">
          Review your character before submitting for approval.
        </p>
      </div>

      {/* Application Status Banner */}
      {hasApplication && appStatus && <ApplicationBanner application={application.data!} />}

      {/* Validation Summary (only when no active application) */}
      {!hasApplication && incompleteStages.length > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              <CardTitle className="text-base">Incomplete Sections</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-sm text-muted-foreground">
              Please complete these sections before submitting:
            </p>
            <ul className="space-y-1">
              {incompleteStages.map((stage) => (
                <li key={stage}>
                  <button
                    onClick={() => onStageSelect(stage)}
                    className="text-sm text-primary underline-offset-4 hover:underline"
                  >
                    {STAGE_LABELS[stage]}
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Unspent CG Points Banner */}
      {!hasApplication && hasUnspentPoints && (
        <Card className="border-blue-500/50 bg-blue-500/10">
          <CardContent className="flex items-start gap-3 pt-6">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-blue-500" />
            <p className="text-sm text-muted-foreground">
              You have <strong className="text-foreground">{cgRemaining} unspent CG points</strong>.
              If you submit now, these will convert to{' '}
              <strong className="text-foreground">{bonusXP} bonus XP</strong> on your character. You
              can go back to earlier stages to spend them if you prefer.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Character Sheet Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{fullName}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Basic Info */}
          <section className="grid gap-4 sm:grid-cols-2">
            <InfoRow label="Homeland" value={draft.selected_area?.name} />
            <InfoRow label="Beginnings" value={draft.selected_beginnings?.name ?? 'Unknown'} />
            <InfoRow label="Species" value={draft.selected_species?.name} />
            <InfoRow label="Gender" value={draft.selected_gender?.display_name} />
            <InfoRow label="Age" value={draft.age?.toString()} />
          </section>

          <Separator />

          {/* Lineage */}
          <section>
            <h4 className="mb-2 font-semibold">Lineage</h4>
            <InfoRow
              label="Family"
              value={
                draft.is_orphan
                  ? 'Orphan / No Family'
                  : (draft.family?.name ??
                    (draft.selected_beginnings?.family_known === false ? 'Unknown' : ''))
              }
            />
          </section>

          {draftData.description && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Description</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.description}
                </p>
              </section>
            </>
          )}

          {draftData.personality && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Personality</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.personality}
                </p>
              </section>
            </>
          )}

          {draftData.background && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Background</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.background}
                </p>
              </section>
            </>
          )}
        </CardContent>
      </Card>

      {/* Action Area - depends on application state */}
      {!hasApplication && (
        <NoApplicationActions
          canSubmit={canSubmit}
          isStaff={isStaff}
          submissionNotes={submissionNotes}
          onNotesChange={setSubmissionNotes}
          onSubmit={handleSubmit}
          submitPending={submitDraft.isPending}
          onAddToRoster={() => addToRoster.mutate(draft.id)}
          addToRosterPending={addToRoster.isPending}
        />
      )}

      {hasApplication && (appStatus === 'submitted' || appStatus === 'in_review') && (
        <SubmittedActions
          appStatus={appStatus}
          onUnsubmit={handleUnsubmit}
          unsubmitPending={unsubmit.isPending}
          onWithdraw={handleWithdraw}
          withdrawPending={withdraw.isPending}
        />
      )}

      {hasApplication && appStatus === 'revisions_requested' && (
        <RevisionsActions
          resubmitComment={resubmitComment}
          onCommentChange={setResubmitComment}
          onResubmit={handleResubmit}
          resubmitPending={resubmit.isPending}
          onWithdraw={handleWithdraw}
          withdrawPending={withdraw.isPending}
        />
      )}

      {hasApplication && (appStatus === 'denied' || appStatus === 'withdrawn') && (
        <TerminalActions />
      )}

      {/* Error display */}
      {(submitDraft.isError ||
        addToRoster.isError ||
        unsubmit.isError ||
        withdraw.isError ||
        resubmit.isError) && (
        <p className="text-sm text-destructive">An error occurred. Please try again.</p>
      )}

      {/* CG Points Conversion Confirmation Modal */}
      <Dialog open={showConversionModal} onOpenChange={setShowConversionModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unspent CG Points</DialogTitle>
            <DialogDescription>
              You have <strong>{cgRemaining} unspent CG points</strong> that will convert to{' '}
              <strong>{bonusXP} bonus XP</strong> locked to this character. Are you sure you want to
              submit?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConversionModal(false)}>
              Go Back
            </Button>
            <Button onClick={handleConfirmSubmit}>Submit Anyway</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}

// =============================================================================
// Application Status Banner
// =============================================================================

interface ApplicationBannerProps {
  application: {
    status: ApplicationStatus;
    reviewer_name: string | null;
    expires_at: string | null;
  };
}

const BANNER_STYLES: Record<
  ApplicationStatus,
  { border: string; bg: string; Icon: typeof Clock; iconClass: string }
> = {
  submitted: {
    border: 'border-blue-500/50',
    bg: 'bg-blue-500/10',
    Icon: Clock,
    iconClass: 'text-blue-500',
  },
  in_review: {
    border: 'border-blue-500/50',
    bg: 'bg-blue-500/10',
    Icon: Clock,
    iconClass: 'text-blue-500',
  },
  revisions_requested: {
    border: 'border-yellow-500/50',
    bg: 'bg-yellow-500/10',
    Icon: MessageSquare,
    iconClass: 'text-yellow-500',
  },
  approved: {
    border: 'border-green-500/50',
    bg: 'bg-green-500/10',
    Icon: Send,
    iconClass: 'text-green-500',
  },
  denied: {
    border: 'border-red-500/50',
    bg: 'bg-red-500/10',
    Icon: XCircle,
    iconClass: 'text-red-500',
  },
  withdrawn: {
    border: 'border-muted-foreground/50',
    bg: 'bg-muted/50',
    Icon: XCircle,
    iconClass: 'text-muted-foreground',
  },
};

function getBannerMessage(
  status: ApplicationStatus,
  reviewerName: string | null,
  expiresAt: string | null
): string {
  switch (status) {
    case 'submitted':
      return 'Your character has been submitted and is awaiting review.';
    case 'in_review':
      return reviewerName
        ? `Your character is being reviewed by ${reviewerName}.`
        : 'Your character is under review.';
    case 'revisions_requested':
      return 'Revisions requested. Check the application thread for staff feedback.';
    case 'approved':
      return 'Your character has been approved!';
    case 'denied':
      return expiresAt
        ? `This application was denied. Draft expires on ${new Date(expiresAt).toLocaleDateString()}.`
        : 'This application was denied.';
    case 'withdrawn':
      return expiresAt
        ? `This application was withdrawn. Draft expires on ${new Date(expiresAt).toLocaleDateString()}.`
        : 'This application was withdrawn.';
  }
}

function ApplicationBanner({ application }: ApplicationBannerProps) {
  const { status, reviewer_name, expires_at } = application;
  const { border, bg, Icon, iconClass } = BANNER_STYLES[status];
  const message = getBannerMessage(status, reviewer_name, expires_at);

  return (
    <Card className={cn(border, bg)}>
      <CardContent className="flex items-start gap-3 pt-6">
        <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', iconClass)} />
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant(status)}>{statusLabel(status)}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{message}</p>
          <Link
            to="/characters/create/application"
            className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View Application Thread
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// State 1: No Application - Submit with notes
// =============================================================================

interface NoApplicationActionsProps {
  canSubmit: boolean;
  isStaff: boolean;
  submissionNotes: string;
  onNotesChange: (notes: string) => void;
  onSubmit: () => void;
  submitPending: boolean;
  onAddToRoster: () => void;
  addToRosterPending: boolean;
}

function NoApplicationActions({
  canSubmit,
  isStaff,
  submissionNotes,
  onNotesChange,
  onSubmit,
  submitPending,
  onAddToRoster,
  addToRosterPending,
}: NoApplicationActionsProps) {
  return (
    <div className="space-y-4">
      {/* Submission Notes */}
      <div className="space-y-2">
        <label htmlFor="submission-notes" className="text-sm font-medium">
          Notes for Reviewers <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Textarea
          id="submission-notes"
          placeholder="Any context or notes for the staff reviewing your character..."
          value={submissionNotes}
          onChange={(e) => onNotesChange(e.target.value)}
          rows={3}
          className="resize-y"
        />
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-4">
        <Button size="lg" disabled={!canSubmit || submitPending} onClick={onSubmit}>
          {submitPending ? (
            'Submitting...'
          ) : (
            <>
              <Send className="mr-2 h-4 w-4" />
              Submit for Review
            </>
          )}
        </Button>

        {isStaff && (
          <Button
            size="lg"
            variant="secondary"
            disabled={!canSubmit || addToRosterPending}
            onClick={onAddToRoster}
          >
            {addToRosterPending ? (
              'Adding...'
            ) : (
              <>
                <UserPlus className="mr-2 h-4 w-4" />
                Add to Roster
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// State 2: Submitted / In Review - Unsubmit or Withdraw
// =============================================================================

interface SubmittedActionsProps {
  appStatus: 'submitted' | 'in_review';
  onUnsubmit: () => void;
  unsubmitPending: boolean;
  onWithdraw: () => void;
  withdrawPending: boolean;
}

function SubmittedActions({
  appStatus,
  onUnsubmit,
  unsubmitPending,
  onWithdraw,
  withdrawPending,
}: SubmittedActionsProps) {
  return (
    <div className="flex flex-wrap gap-4">
      {appStatus === 'submitted' && (
        <Button variant="outline" size="lg" disabled={unsubmitPending} onClick={onUnsubmit}>
          {unsubmitPending ? (
            'Un-submitting...'
          ) : (
            <>
              <Undo2 className="mr-2 h-4 w-4" />
              Un-submit to Edit
            </>
          )}
        </Button>
      )}
      <Button variant="destructive" size="lg" disabled={withdrawPending} onClick={onWithdraw}>
        {withdrawPending ? (
          'Withdrawing...'
        ) : (
          <>
            <XCircle className="mr-2 h-4 w-4" />
            Withdraw Application
          </>
        )}
      </Button>
    </div>
  );
}

// =============================================================================
// State 3: Revisions Requested - Resubmit or Withdraw
// =============================================================================

interface RevisionsActionsProps {
  resubmitComment: string;
  onCommentChange: (comment: string) => void;
  onResubmit: () => void;
  resubmitPending: boolean;
  onWithdraw: () => void;
  withdrawPending: boolean;
}

function RevisionsActions({
  resubmitComment,
  onCommentChange,
  onResubmit,
  resubmitPending,
  onWithdraw,
  withdrawPending,
}: RevisionsActionsProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label htmlFor="resubmit-comment" className="text-sm font-medium">
          Comment for Reviewers{' '}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Textarea
          id="resubmit-comment"
          placeholder="Describe the changes you made in response to feedback..."
          value={resubmitComment}
          onChange={(e) => onCommentChange(e.target.value)}
          rows={3}
          className="resize-y"
        />
      </div>

      <div className="flex flex-wrap gap-4">
        <Button size="lg" disabled={resubmitPending} onClick={onResubmit}>
          {resubmitPending ? (
            'Resubmitting...'
          ) : (
            <>
              <Send className="mr-2 h-4 w-4" />
              Resubmit for Review
            </>
          )}
        </Button>
        <Button variant="destructive" size="lg" disabled={withdrawPending} onClick={onWithdraw}>
          {withdrawPending ? (
            'Withdrawing...'
          ) : (
            <>
              <XCircle className="mr-2 h-4 w-4" />
              Withdraw Application
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

// =============================================================================
// State 4: Denied / Withdrawn - Read-only, link to thread
// =============================================================================

function TerminalActions() {
  return (
    <div className="flex flex-wrap gap-4">
      <Button variant="outline" size="lg" asChild>
        <Link to="/characters/create/application">
          <ExternalLink className="mr-2 h-4 w-4" />
          View Application Thread
        </Link>
      </Button>
    </div>
  );
}

// =============================================================================
// Shared Components
// =============================================================================

interface InfoRowProps {
  label: string;
  value: string | undefined;
}

function InfoRow({ label, value }: InfoRowProps) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn(!value && 'italic text-muted-foreground')}>{value ?? 'Not set'}</span>
    </div>
  );
}
