import { submitBugReport } from '@/submissions/api';
import { SubmissionForm } from '@/submissions/SubmissionForm';

export function BugReportPage() {
  return (
    <SubmissionForm
      title="Report a Bug"
      intro="Describe what you were doing, what you expected to happen, and what actually happened. Include any error messages."
      placeholder="Steps to reproduce, expected behavior, actual behavior..."
      successMessage="Thanks — staff will investigate."
      submitFn={submitBugReport}
    />
  );
}
