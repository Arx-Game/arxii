import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { PaginatedResponse } from '@/shared/types';
import type { DraftApplication } from '@/character-creation/types';
import {
  addStaffComment,
  approveApplication,
  claimApplication,
  denyApplication,
  getApplicationDetail,
  getApplications,
  getPendingApplicationCount,
  requestApplicationRevisions,
} from '@/character-creation/api';
import type {
  AccountHistory,
  BugReport,
  GMApplication,
  InboxResponse,
  PlayerFeedback,
  PlayerReport,
  SubmissionCategory,
  SubmissionStatus,
} from './types';
import {
  getStaffInbox,
  getAccountHistory,
  getFeedbackList,
  getFeedbackDetail,
  updateFeedbackStatus,
  getBugReportList,
  getBugReportDetail,
  updateBugReportStatus,
  getPlayerReportList,
  getPlayerReportDetail,
  updatePlayerReportStatus,
  getOpenSubmissionCount,
  getGMApplicationList,
  getGMApplicationDetail,
  updateGMApplication,
} from './api';

export const staffKeys = {
  all: ['staff'] as const,
  applications: (status?: string) => [...staffKeys.all, 'applications', status] as const,
  application: (id: number) => [...staffKeys.all, 'application', id] as const,
  pendingCount: () => [...staffKeys.all, 'pending-count'] as const,
  inbox: (categories?: SubmissionCategory[], page?: number) =>
    [...staffKeys.all, 'inbox', categories, page] as const,
  inboxCount: () => [...staffKeys.all, 'inbox-count'] as const,
  feedback: (status?: string, page?: number) =>
    [...staffKeys.all, 'feedback', status, page] as const,
  feedbackDetail: (id: number) => [...staffKeys.all, 'feedback-detail', id] as const,
  bugReports: (status?: string, page?: number) =>
    [...staffKeys.all, 'bug-reports', status, page] as const,
  bugReportDetail: (id: number) => [...staffKeys.all, 'bug-report-detail', id] as const,
  playerReports: (status?: string, page?: number) =>
    [...staffKeys.all, 'player-reports', status, page] as const,
  playerReportDetail: (id: number) => [...staffKeys.all, 'player-report-detail', id] as const,
  accountHistory: (id: number) => [...staffKeys.all, 'account-history', id] as const,
  gmApplications: (status?: string, page?: number) =>
    [...staffKeys.all, 'gm-applications', status, page] as const,
  gmApplicationDetail: (id: number) => [...staffKeys.all, 'gm-application-detail', id] as const,
};

export function useApplications(statusFilter?: string) {
  return useQuery<PaginatedResponse<DraftApplication>>({
    queryKey: staffKeys.applications(statusFilter),
    queryFn: () => getApplications(statusFilter),
  });
}

export function useApplicationDetail(id: number | undefined) {
  return useQuery({
    queryKey: staffKeys.application(id!),
    queryFn: () => getApplicationDetail(id!),
    enabled: !!id,
  });
}

export function usePendingApplicationCount(enabled = true) {
  return useQuery({
    queryKey: staffKeys.pendingCount(),
    queryFn: getPendingApplicationCount,
    refetchInterval: 60_000,
    enabled,
  });
}

export function useClaimApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: claimApplication,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useApproveApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment?: string }) =>
      approveApplication(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useRequestRevisions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      requestApplicationRevisions(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useDenyApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) => denyApplication(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useAddStaffComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => addStaffComment(id, text),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: staffKeys.application(id) });
    },
  });
}

// =============================================================================
// Staff Inbox Hooks
// =============================================================================

export function useStaffInbox(categories?: SubmissionCategory[], page?: number) {
  return useQuery<InboxResponse>({
    queryKey: staffKeys.inbox(categories, page),
    queryFn: () => getStaffInbox(categories, page),
  });
}

export function useOpenSubmissionCount(enabled = true) {
  return useQuery<number>({
    queryKey: staffKeys.inboxCount(),
    queryFn: getOpenSubmissionCount,
    refetchInterval: 60_000,
    enabled,
  });
}

// =============================================================================
// Player Feedback Hooks
// =============================================================================

export function useFeedbackList(status?: SubmissionStatus, page?: number) {
  return useQuery<PaginatedResponse<PlayerFeedback>>({
    queryKey: staffKeys.feedback(status, page),
    queryFn: () => getFeedbackList(status, page),
  });
}

export function useFeedbackDetail(id: number | undefined) {
  return useQuery<PlayerFeedback>({
    queryKey: staffKeys.feedbackDetail(id!),
    queryFn: () => getFeedbackDetail(id!),
    enabled: !!id,
  });
}

export function useUpdateFeedbackStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: SubmissionStatus }) =>
      updateFeedbackStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

// =============================================================================
// Bug Report Hooks
// =============================================================================

export function useBugReportList(status?: SubmissionStatus, page?: number) {
  return useQuery<PaginatedResponse<BugReport>>({
    queryKey: staffKeys.bugReports(status, page),
    queryFn: () => getBugReportList(status, page),
  });
}

export function useBugReportDetail(id: number | undefined) {
  return useQuery<BugReport>({
    queryKey: staffKeys.bugReportDetail(id!),
    queryFn: () => getBugReportDetail(id!),
    enabled: !!id,
  });
}

export function useUpdateBugReportStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: SubmissionStatus }) =>
      updateBugReportStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

// =============================================================================
// Player Report Hooks
// =============================================================================

export function usePlayerReportList(status?: SubmissionStatus, page?: number) {
  return useQuery<PaginatedResponse<PlayerReport>>({
    queryKey: staffKeys.playerReports(status, page),
    queryFn: () => getPlayerReportList(status, page),
  });
}

export function usePlayerReportDetail(id: number | undefined) {
  return useQuery<PlayerReport>({
    queryKey: staffKeys.playerReportDetail(id!),
    queryFn: () => getPlayerReportDetail(id!),
    enabled: !!id,
  });
}

export function useUpdatePlayerReportStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: SubmissionStatus }) =>
      updatePlayerReportStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

// =============================================================================
// GM Application Hooks
// =============================================================================

export function useGMApplicationList(status?: string, page?: number) {
  return useQuery<PaginatedResponse<GMApplication>>({
    queryKey: staffKeys.gmApplications(status, page),
    queryFn: () => getGMApplicationList(status, page),
  });
}

export function useGMApplicationDetail(id: number | undefined) {
  return useQuery<GMApplication>({
    queryKey: staffKeys.gmApplicationDetail(id!),
    queryFn: () => getGMApplicationDetail(id!),
    enabled: !!id,
  });
}

export function useUpdateGMApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: number;
      data: { status?: string; staff_response?: string };
    }) => updateGMApplication(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

// =============================================================================
// Account History Hook
// =============================================================================

export function useAccountHistory(accountId: number | undefined) {
  return useQuery<AccountHistory>({
    queryKey: staffKeys.accountHistory(accountId!),
    queryFn: () => getAccountHistory(accountId!),
    enabled: !!accountId,
  });
}
