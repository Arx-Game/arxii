import { submitFeedback } from '@/submissions/api';
import { SubmissionForm } from '@/submissions/SubmissionForm';

export function FeedbackPage() {
  return (
    <SubmissionForm
      title="Send Feedback"
      intro="Have thoughts on the game, a suggestion, or something you'd like us to know? Let us know below. Staff reviews all feedback."
      placeholder="What's on your mind?"
      successMessage="Thanks for your feedback — staff will review it."
      submitFn={submitFeedback}
    />
  );
}
