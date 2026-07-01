import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchCategories,
  fetchPreference,
  updatePreference,
  createPreference,
  fetchCategoryRules,
  upsertCategoryRule,
  deleteCategoryRule,
  fetchWhitelist,
  addWhitelist,
  removeWhitelist,
  fetchBlacklist,
  addBlacklist,
  removeBlacklist,
} from './api';
import type {
  SocialConsentPreferenceRequest,
  SocialConsentCategoryRuleRequest,
  SocialConsentWhitelistRequest,
  SocialConsentBlacklistRequest,
  PaginatedSocialConsentCategoryList,
  PaginatedSocialConsentCategoryRuleList,
  PaginatedSocialConsentWhitelistList,
  PaginatedSocialConsentBlacklistList,
} from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const consentKeys = {
  categories: () => ['consent', 'categories'] as const,
  preference: (tenureId: number) => ['consent', 'preference', tenureId] as const,
  categoryRules: (preferenceId: number) => ['consent', 'category-rules', preferenceId] as const,
  whitelist: (tenureId: number, categoryId: number) =>
    ['consent', 'whitelist', tenureId, categoryId] as const,
  blacklist: (tenureId: number, categoryId: number) =>
    ['consent', 'blacklist', tenureId, categoryId] as const,
};

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export function useConsentCategories() {
  return useQuery<PaginatedSocialConsentCategoryList>({
    queryKey: consentKeys.categories(),
    queryFn: fetchCategories,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Preference
// ---------------------------------------------------------------------------

export function useConsentPreference(tenureId: number | undefined) {
  return useQuery({
    queryKey: consentKeys.preference(tenureId!),
    queryFn: () => fetchPreference(tenureId!),
    enabled: !!tenureId,
    throwOnError: true,
  });
}

export function useUpdatePreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<SocialConsentPreferenceRequest> }) =>
      updatePreference(id, body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.preference(data.tenure) });
    },
  });
}

export function useCreatePreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SocialConsentPreferenceRequest) => createPreference(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.preference(data.tenure) });
    },
  });
}

// ---------------------------------------------------------------------------
// Category rules
// (useCategoryRules takes a tenureId; it derives preferenceId from the
// preference query so the hook only fires once the preference is loaded.)
// ---------------------------------------------------------------------------

export function useCategoryRules(tenureId: number | undefined) {
  const { data: preference } = useConsentPreference(tenureId);
  const preferenceId = preference?.id;

  return useQuery<PaginatedSocialConsentCategoryRuleList>({
    queryKey: consentKeys.categoryRules(preferenceId!),
    queryFn: () => fetchCategoryRules(preferenceId!),
    enabled: !!preferenceId,
    throwOnError: true,
  });
}

export function useUpsertCategoryRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SocialConsentCategoryRuleRequest) => upsertCategoryRule(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.categoryRules(data.preference) });
    },
  });
}

export function useDeleteCategoryRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, preferenceId }: { id: number; preferenceId: number }) =>
      deleteCategoryRule(id).then(() => ({ preferenceId })),
    onSuccess: ({ preferenceId }) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.categoryRules(preferenceId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Whitelist
// ---------------------------------------------------------------------------

export function useWhitelist(tenureId: number | undefined, categoryId: number | undefined) {
  return useQuery<PaginatedSocialConsentWhitelistList>({
    queryKey: consentKeys.whitelist(tenureId!, categoryId!),
    queryFn: () => fetchWhitelist(tenureId!, categoryId!),
    enabled: !!tenureId && !!categoryId,
    throwOnError: true,
  });
}

export function useAddWhitelist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SocialConsentWhitelistRequest) => addWhitelist(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: consentKeys.whitelist(data.owner_tenure, data.category),
      });
    },
  });
}

export function useRemoveWhitelist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ownerTenureId,
      categoryId,
    }: {
      id: number;
      ownerTenureId: number;
      categoryId: number;
    }) => removeWhitelist(id).then(() => ({ ownerTenureId, categoryId })),
    onSuccess: ({ ownerTenureId, categoryId }) => {
      queryClient.invalidateQueries({
        queryKey: consentKeys.whitelist(ownerTenureId, categoryId),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Blacklist (#1698)
// ---------------------------------------------------------------------------

export function useBlacklist(tenureId: number | undefined, categoryId: number | undefined) {
  return useQuery<PaginatedSocialConsentBlacklistList>({
    queryKey: consentKeys.blacklist(tenureId!, categoryId!),
    queryFn: () => fetchBlacklist(tenureId!, categoryId!),
    enabled: !!tenureId && !!categoryId,
    throwOnError: true,
  });
}

export function useAddBlacklist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SocialConsentBlacklistRequest) => addBlacklist(body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: consentKeys.blacklist(data.owner_tenure, data.category),
      });
    },
  });
}

export function useRemoveBlacklist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ownerTenureId,
      categoryId,
    }: {
      id: number;
      ownerTenureId: number;
      categoryId: number;
    }) => removeBlacklist(id).then(() => ({ ownerTenureId, categoryId })),
    onSuccess: ({ ownerTenureId, categoryId }) => {
      queryClient.invalidateQueries({
        queryKey: consentKeys.blacklist(ownerTenureId, categoryId),
      });
    },
  });
}
