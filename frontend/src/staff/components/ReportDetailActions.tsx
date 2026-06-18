import { Button } from '@/components/ui/button';
import { FileGithubIssueDialog } from '@/staff/components/FileGithubIssueDialog';
import type { IssueDraft } from '@/staff/types';

interface ReportDetailActionsProps {
  status: string;
  isUpdating: boolean;
  onReview: () => void;
  onDismiss: () => void;
  issueUrl: string;
  issueNumber: number | null;
  issueDraft: IssueDraft;
  isFiling: boolean;
  onFileIssue: (title: string, body: string) => Promise<unknown>;
}

/** The shared action row on a report detail page (#1164): status transitions while
 *  the report is open, plus the File GitHub issue control. */
export function ReportDetailActions({
  status,
  isUpdating,
  onReview,
  onDismiss,
  issueUrl,
  issueNumber,
  issueDraft,
  isFiling,
  onFileIssue,
}: ReportDetailActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {status === 'open' && (
        <>
          <Button disabled={isUpdating} onClick={onReview}>
            Mark Reviewed
          </Button>
          <Button variant="outline" disabled={isUpdating} onClick={onDismiss}>
            Dismiss
          </Button>
        </>
      )}
      <FileGithubIssueDialog
        issueUrl={issueUrl}
        issueNumber={issueNumber}
        draft={issueDraft}
        isPending={isFiling}
        onSubmit={onFileIssue}
      />
    </div>
  );
}
