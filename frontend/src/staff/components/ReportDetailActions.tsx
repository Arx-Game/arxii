import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { FileGithubIssueDialog } from '@/staff/components/FileGithubIssueDialog';
import type { IssueDraft } from '@/staff/types';

interface ReportWithIssue {
  id: number;
  status: string;
  github_issue_url: string;
  github_issue_number: number | null;
  issue_draft: IssueDraft;
}

// Minimal structural shapes of the react-query mutations used here, so the same
// component serves both the bug-report and system-error hooks without coupling to
// either's concrete generics.
interface StatusMutation {
  mutate: (
    vars: { id: number; status: 'reviewed' | 'dismissed' },
    options?: { onSuccess?: () => void }
  ) => void;
  isPending: boolean;
}

interface FileIssueMutation {
  mutateAsync: (vars: { id: number; title: string; body: string }) => Promise<unknown>;
  isPending: boolean;
}

interface ReportDetailActionsProps {
  report: ReportWithIssue;
  updateStatus: StatusMutation;
  fileIssue: FileIssueMutation;
  /** Where to return after a status transition (the report's list page). */
  listPath: string;
}

/** The shared action row on a report detail page (#1164): status transitions while
 *  the report is open, plus the File GitHub issue control. Owns the status handler and
 *  post-transition navigation so each detail page just supplies its data + list path. */
export function ReportDetailActions({
  report,
  updateStatus,
  fileIssue,
  listPath,
}: ReportDetailActionsProps) {
  const navigate = useNavigate();

  function changeStatus(status: 'reviewed' | 'dismissed') {
    updateStatus.mutate({ id: report.id, status }, { onSuccess: () => navigate(listPath) });
  }

  return (
    <div className="flex flex-wrap gap-2">
      {report.status === 'open' && (
        <>
          <Button disabled={updateStatus.isPending} onClick={() => changeStatus('reviewed')}>
            Mark Reviewed
          </Button>
          <Button
            variant="outline"
            disabled={updateStatus.isPending}
            onClick={() => changeStatus('dismissed')}
          >
            Dismiss
          </Button>
        </>
      )}
      <FileGithubIssueDialog
        issueUrl={report.github_issue_url}
        issueNumber={report.github_issue_number}
        draft={report.issue_draft}
        isPending={fileIssue.isPending}
        onSubmit={(title, body) => fileIssue.mutateAsync({ id: report.id, title, body })}
      />
    </div>
  );
}
