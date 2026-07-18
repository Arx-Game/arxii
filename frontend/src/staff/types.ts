// Inbox item from /api/staff_inbox/
export interface InboxItem {
  source_type:
    | 'player_feedback'
    | 'bug_report'
    | 'player_report'
    | 'character_application'
    | 'gm_application'
    | 'system_error'
    | 'petition';
  source_pk: number;
  title: string;
  reporter_summary: string;
  created_at: string;
  status: string;
  detail_url: string;
  /** Kudos + standing columns for the sender (#2288); present on petition items. */
  sender_context?: SenderContext | null;
}

/** The sender's staff-contact track record (#2288). */
export interface SenderContext {
  kudos_total: number;
  actioned_count: number;
  dismissed_count: number;
  is_ignored: boolean;
}

// Paginated inbox response (extended pagination from staff_inbox)
export interface InboxResponse {
  count: number;
  next: string | null;
  previous: string | null;
  page_size: number;
  num_pages: number;
  current_page: number;
  results: InboxItem[];
}

// Feedback detail from /api/player_submissions/feedback/{id}/
export interface PlayerFeedback {
  id: number;
  reporter_account: number;
  reporter_account_username: string;
  reporter_persona: number;
  reporter_persona_name: string;
  description: string;
  location: number | null;
  created_at: string;
  status: string;
}

// A redacted, staff-editable draft for the "File GitHub issue" dialog (#1164).
export interface IssueDraft {
  title: string;
  body: string;
  stub_body: string;
}

// Bug report detail from /api/player_submissions/bug-reports/{id}/
export interface BugReport {
  id: number;
  reporter_account: number;
  reporter_account_username: string;
  reporter_persona: number;
  reporter_persona_name: string;
  description: string;
  location: number | null;
  created_at: string;
  status: string;
  github_issue_number: number | null;
  github_issue_url: string;
  issue_draft: IssueDraft;
}

// Player report detail from /api/player_submissions/player-reports/{id}/
export interface PlayerReport {
  id: number;
  reporter_account: number;
  reporter_account_username: string;
  reporter_persona: number;
  reporter_persona_name: string;
  reported_account: number;
  reported_account_username: string;
  reported_persona: number;
  reported_persona_name: string;
  behavior_description: string;
  asked_to_stop: boolean;
  blocked_or_muted: boolean;
  scene: number | null;
  interaction: number | null;
  location: number | null;
  created_at: string;
  status: string;
}

// System error report detail from /api/player_submissions/system-errors/{id}/
// Auto-captured runtime error (#1164) — system-authored, so the only writable field
// is `status`; everything else is captured at report time.
export interface SystemErrorReport {
  id: number;
  signature: string;
  label: string;
  exception_type: string;
  message: string;
  traceback: string;
  actor_persona: number | null;
  actor_persona_name: string | null;
  occurrence_count: number;
  first_seen: string;
  last_seen: string;
  status: string;
  github_issue_number: number | null;
  github_issue_url: string;
  issue_draft: IssueDraft;
}

// Response from the file-issue action.
export interface FiledIssue {
  github_issue_number: number | null;
  github_issue_url: string;
}

// Account history response from /api/staff_inbox/accounts/{id}/history/
export interface AccountHistoryCategory {
  items: InboxItem[];
  total: number;
  truncated: boolean;
}

export interface AccountHistory {
  reports_against: AccountHistoryCategory;
  reports_submitted: AccountHistoryCategory;
  feedback: AccountHistoryCategory;
  bug_reports: AccountHistoryCategory;
  character_applications: AccountHistoryCategory;
  gm_applications: AccountHistoryCategory;
}

// GM application detail from /api/gm/applications/{id}/
export interface GMApplication {
  id: number;
  account: number;
  account_username: string;
  application_text: string;
  staff_response: string;
  status: string;
  created_at: string;
  updated_at: string;
  reviewed_by: number | null;
  reviewed_by_username: string | null;
}

export type GMApplicationStatus = 'pending' | 'approved' | 'denied' | 'withdrawn';

// Submission status values
export type SubmissionStatus = 'open' | 'reviewed' | 'dismissed';

// Category values for inbox filtering
export type SubmissionCategory =
  | 'player_feedback'
  | 'bug_report'
  | 'player_report'
  | 'character_application'
  | 'gm_application'
  | 'system_error'
  | 'petition';
