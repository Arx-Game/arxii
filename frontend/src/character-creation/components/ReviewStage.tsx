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

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTables } from '@/tables/queries';
import type { GMTable } from '@/tables/types';
import { ExternalLink } from 'lucide-react';
import { ChapterLeaf, Marginalia, Note, NightPlate } from '../folio';
import { FinalizeForTableDialog } from './FinalizeForTableDialog';
import {
  useAddToRoster,
  useCGExplanations,
  useDraftApplication,
  useDraftCGPoints,
  useResubmitDraft,
  useSubmitDraft,
  useUnsubmitDraft,
  useWithdrawDraft,
} from '../queries';
import type { ApplicationStatus, CharacterDraft } from '../types';
import { Stage, STAGE_LABELS } from '../types';
import { composeFullName } from '../utils';

interface ReviewStageProps {
  draft: CharacterDraft;
  isStaff: boolean;
  onStageSelect: (stage: Stage) => void;
}

export function ReviewStage({ draft, isStaff, onStageSelect }: ReviewStageProps) {
  const navigate = useNavigate();
  const submitDraft = useSubmitDraft();
  const { data: copy } = useCGExplanations();
  const addToRoster = useAddToRoster();
  const application = useDraftApplication(draft.id);
  const unsubmit = useUnsubmitDraft();
  const withdraw = useWithdrawDraft();
  const resubmit = useResubmitDraft();

  const cgPoints = useDraftCGPoints(draft.id);

  // Active tables this (non-staff) account GMs — gates the "Finalize for My
  // Table" flow (#3268). `useTables()` returns every table the requester has
  // any relationship to; `viewer_role` narrows to ones they own as GM.
  const tablesQuery = useTables({ status: 'active' });
  const ownedGMTables: GMTable[] = (tablesQuery.data?.results ?? []).filter(
    (table) => table.viewer_role === 'gm'
  );

  const [submissionNotes, setSubmissionNotes] = useState('');
  const [resubmitComment, setResubmitComment] = useState('');
  const [showConversionModal, setShowConversionModal] = useState(false);
  const [showFinalizeForTable, setShowFinalizeForTable] = useState(false);

  const stageCompletion = draft.stage_completion;
  const incompleteStages = Object.entries(stageCompletion)
    .filter(([stage, complete]) => !complete && parseInt(stage) !== Stage.REVIEW)
    .map(([stage]) => parseInt(stage) as Stage);

  const canSubmit = incompleteStages.length === 0;
  const draftData = draft.draft_data;
  // Both arms of the old ternary here returned '', so family_known never affected
  // the result. Reduced to what it actually evaluated to; if an unknown family was
  // meant to read differently, that behaviour was never present to preserve.
  const familyName = draft.family?.name ?? '';
  // Unlike familyName above (which feeds composeFullName and must stay blank),
  // the review row spells out a deliberately-unknown family.
  const unknownFamily = draft.selected_beginnings?.family_known === false ? 'Unknown' : '';
  const familyDisplay = draft.draft_data.lineage_is_orphan
    ? 'Orphan / No Family'
    : (draft.family?.name ?? unknownFamily);
  const fullName = composeFullName(draftData.first_name, familyName, 'Unnamed Character');

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

  const written: { label: string; text?: string; stage: Stage }[] = [
    {
      label: copy?.review_glimpse_label ?? 'What your character would speak of themselves',
      text: draftData.glimpse_story,
      stage: Stage.GIFT,
    },
    { label: 'Background', text: draftData.background, stage: Stage.IDENTITY },
    { label: 'Description', text: draftData.description, stage: Stage.APPEARANCE },
    { label: 'Personality', text: draftData.personality, stage: Stage.IDENTITY },
  ];
  const months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];
  const birthday =
    draft.birthday_month && draft.birthday_day
      ? `${months[draft.birthday_month - 1]} ${draft.birthday_day}`
      : undefined;
  const record: { label: string; value?: string; stage: Stage }[] = [
    { label: 'Homeland', value: draft.selected_area?.name, stage: Stage.ORIGIN },
    { label: 'Beginnings', value: draft.selected_beginnings?.name, stage: Stage.HERITAGE },
    { label: 'Species', value: draft.selected_species?.name, stage: Stage.HERITAGE },
    { label: 'Gender', value: draft.selected_gender?.display_name, stage: Stage.HERITAGE },
    { label: 'Age', value: draft.age?.toString(), stage: Stage.HERITAGE },
    { label: 'Birthday', value: birthday, stage: Stage.HERITAGE },
    { label: 'Family', value: familyDisplay, stage: Stage.LINEAGE },
    { label: 'Path', value: draft.selected_path?.name, stage: Stage.PATH },
    { label: 'Tradition', value: draft.selected_tradition?.name, stage: Stage.GIFT },
  ];
  const firstIncomplete = incompleteStages[0];
  const submitted = hasApplication && (appStatus === 'submitted' || appStatus === 'in_review');

  // Focus moves to the second night plate's title the moment the record
  // closes (design law §1). Tracked as a false-to-true transition rather
  // than a submit-mutation callback, so a page load that already finds a
  // submitted draft does not steal focus on mount.
  const wasSubmittedRef = useRef(submitted);
  useEffect(() => {
    if (submitted && !wasSubmittedRef.current) {
      requestAnimationFrame(() => document.getElementById('after-title')?.focus());
    }
    wasSubmittedRef.current = submitted;
  }, [submitted]);

  return (
    <>
      <ChapterLeaf
        stage={Stage.REVIEW}
        title={copy?.review_heading ?? 'Your Testament'}
        intro={copy?.review_intro}
        className="review"
        aside={
          <Marginalia id="note-rite">
            {/* PLACEHOLDER: Apostate rewrite */}
            <Note lead="Nothing is final">
              until staff approve the testament. Any chapter may be reopened until then.
            </Note>
          </Marginalia>
        }
      >
        {copy?.review_epigraph && (
          <div className="epigraph">
            <blockquote>
              “<span>{copy.review_epigraph}</span>”
            </blockquote>
            <cite>The Ritual of the Durance</cite>
          </div>
        )}
        <p className="plate-name">{fullName}</p>
        <p className="plate-kicker">
          {[draft.selected_beginnings?.name, familyDisplay, draft.selected_area?.name]
            .filter(Boolean)
            .join(' · ')}
        </p>

        {written
          .filter((w) => w.text)
          .map((w) => (
            <div className="written" key={w.label}>
              <span className="written-label">{w.label}</span>
              <blockquote>
                “<span>{w.text}</span>”
              </blockquote>
              <button type="button" className="quiet-link" onClick={() => onStageSelect(w.stage)}>
                Rewrite in {STAGE_LABELS[w.stage]}
              </button>
            </div>
          ))}

        <div
          className="record-frame"
          style={{ ['--rows' as string]: Math.ceil(record.length / 2) }}
        >
          <h2>{copy?.review_record_heading ?? 'The Record'}</h2>
          <dl>
            {record.map((r) => (
              <div className="row" key={r.label}>
                <dt>{r.label}</dt>
                <dd>
                  {r.value ? (
                    <button type="button" onClick={() => onStageSelect(r.stage)}>
                      {r.value}
                    </button>
                  ) : (
                    <span className="unwritten">not set</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {hasUnspentPoints && (
            // PLACEHOLDER: Apostate rewrite
            <p className="frame-ledger">
              {cgRemaining} points remain unspent; they convert to {bonusXP} experience when the
              testament is approved.
            </p>
          )}
        </div>

        {!hasApplication && (
          <NoApplicationActions
            canSubmit={canSubmit}
            reason={
              firstIncomplete !== undefined ? (
                <>
                  One chapter is still unwritten:{' '}
                  <button
                    type="button"
                    className="quiet-link"
                    id="incomplete-link"
                    onClick={() => onStageSelect(firstIncomplete)}
                  >
                    {STAGE_LABELS[firstIncomplete]}
                  </button>
                  .
                </>
              ) : undefined
            }
            isStaff={isStaff}
            submissionNotes={submissionNotes}
            onNotesChange={setSubmissionNotes}
            onSubmit={handleSubmit}
            submitPending={submitDraft.isPending}
            onAddToRoster={() => addToRoster.mutate(draft.id)}
            addToRosterPending={addToRoster.isPending}
            hasGMTable={ownedGMTables.length > 0}
            onFinalizeForTable={() => setShowFinalizeForTable(true)}
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
        {hasApplication && appStatus === 'approved' && (
          <div className="plate-door">
            <p className="ledger-line">
              {getBannerMessage(
                appStatus,
                application.data!.reviewer_name,
                application.data!.expires_at,
                copy
              )}
            </p>
            <button type="button" className="btn" onClick={() => navigate('/game')}>
              {copy?.review_approved_enter_world ?? 'Enter the World'}
            </button>
          </div>
        )}
        {hasApplication && (appStatus === 'denied' || appStatus === 'withdrawn') && (
          <>
            <p className="ledger-line">
              {getBannerMessage(
                appStatus,
                application.data!.reviewer_name,
                application.data!.expires_at,
                copy
              )}
            </p>
            <TerminalActions />
          </>
        )}
        {(submitDraft.isError ||
          addToRoster.isError ||
          unsubmit.isError ||
          withdraw.isError ||
          resubmit.isError) && <p className="ledger-line">Something went wrong. Try again.</p>}
        {!submitted && <p className="plate-imprint">As Arx endures, we remember</p>}
      </ChapterLeaf>

      {submitted && (
        <NightPlate
          id="after"
          titleId="after-title"
          titleAs="h2"
          eyebrow="The Durance · Submitted"
          title={getBannerMessage(
            appStatus!,
            application.data!.reviewer_name,
            application.data!.expires_at,
            copy
          )}
          imprint
          quiet={{
            label: 'Read the testament again',
            onClick: () => {
              const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
              document
                .getElementById('chapter-11')
                ?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
            },
          }}
        >
          {/* PLACEHOLDER: Apostate rewrite */}
          <p className="plate-sub">
            You will be told in the Hall when staff have read it. If they ask for revisions, the
            chapters reopen.
          </p>
          <SubmittedActions
            appStatus={appStatus as 'submitted' | 'in_review'}
            onUnsubmit={handleUnsubmit}
            unsubmitPending={unsubmit.isPending}
            onWithdraw={handleWithdraw}
            withdrawPending={withdraw.isPending}
          />
        </NightPlate>
      )}

      {/* CG Points Conversion Confirmation Modal (unchanged) */}
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

      {/* Finalize for My Table (#3268) — player-GM direct-to-roster flow */}
      {!isStaff && ownedGMTables.length > 0 && (
        <FinalizeForTableDialog
          draftId={draft.id}
          tables={ownedGMTables}
          open={showFinalizeForTable}
          onOpenChange={setShowFinalizeForTable}
        />
      )}
    </>
  );
}

// =============================================================================
// Application status message (the second night plate's title / a ledger line)
// =============================================================================

function getBannerMessage(
  status: ApplicationStatus,
  reviewerName: string | null,
  expiresAt: string | null,
  copy: Record<string, string> | undefined
): string {
  switch (status) {
    case 'submitted':
      return (
        copy?.review_banner_submitted ?? 'Your character has been submitted and is awaiting review.'
      );
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

// =============================================================================
// State 1: No Application - Submit with notes
// =============================================================================

interface NoApplicationActionsProps {
  canSubmit: boolean;
  /** The named reason beside the closed door: the first unwritten chapter, as a door back to it. */
  reason?: ReactNode;
  isStaff: boolean;
  submissionNotes: string;
  onNotesChange: (notes: string) => void;
  onSubmit: () => void;
  submitPending: boolean;
  onAddToRoster: () => void;
  addToRosterPending: boolean;
  /** Non-staff account owns at least one active GM-role table (#3268). */
  hasGMTable: boolean;
  onFinalizeForTable: () => void;
}

function NoApplicationActions({
  canSubmit,
  reason,
  isStaff,
  submissionNotes,
  onNotesChange,
  onSubmit,
  submitPending,
  onAddToRoster,
  addToRosterPending,
  hasGMTable,
  onFinalizeForTable,
}: NoApplicationActionsProps) {
  return (
    <>
      <div className="field">
        <label htmlFor="submission-notes">A word to the staff</label>
        <textarea
          id="submission-notes"
          value={submissionNotes}
          onChange={(e) => onNotesChange(e.target.value)}
          rows={3}
        />
        <span className="hint">Read by staff only. It does not enter the record.</span>
      </div>

      <div className="plate-door" id="door">
        {reason && (
          <span className="door-reason" id="door-reason">
            {reason}
          </span>
        )}
        <button
          type="button"
          className="btn"
          aria-disabled={!canSubmit ? 'true' : undefined}
          aria-describedby={!canSubmit ? 'door-reason' : undefined}
          disabled={submitPending}
          onClick={() => {
            if (!canSubmit) {
              document.getElementById('incomplete-link')?.focus();
              return;
            }
            onSubmit();
          }}
        >
          {submitPending ? 'Submitting…' : 'Submit for Review'}
        </button>

        {isStaff && (
          <button
            type="button"
            className="quiet-link"
            disabled={!canSubmit || addToRosterPending}
            onClick={onAddToRoster}
          >
            {addToRosterPending ? 'Adding…' : 'Add to Roster'}
          </button>
        )}

        {!isStaff && hasGMTable && (
          <button
            type="button"
            className="quiet-link"
            disabled={!canSubmit}
            onClick={onFinalizeForTable}
          >
            Finalize for My Table
          </button>
        )}
      </div>
    </>
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
    <div className="plate-door">
      {appStatus === 'submitted' && (
        <button type="button" className="btn-quiet" disabled={unsubmitPending} onClick={onUnsubmit}>
          {unsubmitPending ? 'Un-submitting…' : 'Un-submit to edit'}
        </button>
      )}
      <button type="button" className="btn-quiet" disabled={withdrawPending} onClick={onWithdraw}>
        {withdrawPending ? 'Withdrawing…' : 'Withdraw the testament'}
      </button>
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
    <>
      <div className="field">
        <label htmlFor="resubmit-comment">A word to the staff</label>
        <textarea
          id="resubmit-comment"
          value={resubmitComment}
          onChange={(e) => onCommentChange(e.target.value)}
          rows={3}
        />
        <span className="hint">Read by staff only. It does not enter the record.</span>
      </div>

      <div className="plate-door">
        <button type="button" className="btn" disabled={resubmitPending} onClick={onResubmit}>
          {resubmitPending ? 'Resubmitting…' : 'Resubmit for Review'}
        </button>
        <button type="button" className="btn-quiet" disabled={withdrawPending} onClick={onWithdraw}>
          {withdrawPending ? 'Withdrawing…' : 'Withdraw the testament'}
        </button>
      </div>
    </>
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
