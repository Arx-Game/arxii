// Inbox item from /api/staff_inbox/
export interface InboxItem {
  source_type:
    | 'player_feedback'
    | 'bug_report'
    | 'player_report'
    | 'character_application'
    | 'gm_application';
  source_pk: number;
  title: string;
  reporter_summary: string;
  created_at: string;
  status: string;
  detail_url: string;
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

// Submission status values
export type SubmissionStatus = 'open' | 'reviewed' | 'dismissed';

// Category values for inbox filtering
export type SubmissionCategory =
  | 'player_feedback'
  | 'bug_report'
  | 'player_report'
  | 'character_application'
  | 'gm_application';
