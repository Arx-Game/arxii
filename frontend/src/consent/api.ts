import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type { ConsentModeGuidance } from './consentModes';
import type {
  SocialConsentPreference,
  SocialConsentPreferenceRequest,
  SocialConsentCategoryRule,
  SocialConsentCategoryRuleRequest,
  SocialConsentWhitelist,
  SocialConsentWhitelistRequest,
  SocialConsentBlacklist,
  SocialConsentBlacklistRequest,
} from './types';

type PaginatedCategories = components['schemas']['PaginatedSocialConsentCategoryList'];
type PaginatedCategoryRules = components['schemas']['PaginatedSocialConsentCategoryRuleList'];
type PaginatedWhitelist = components['schemas']['PaginatedSocialConsentWhitelistList'];
type PaginatedBlacklist = components['schemas']['PaginatedSocialConsentBlacklistList'];

// ---------------------------------------------------------------------------
// Categories (read-only)
// ---------------------------------------------------------------------------

export async function fetchCategories(): Promise<PaginatedCategories> {
  const res = await apiFetch('/api/consent/categories/');
  if (!res.ok) {
    throw new Error('Failed to load consent categories');
  }
  return res.json();
}

export async function fetchConsentModes(): Promise<ConsentModeGuidance[]> {
  // Not paginated — the modes action returns a plain list of {value, label, guidance} (#2170).
  const res = await apiFetch('/api/consent/categories/modes/');
  if (!res.ok) {
    throw new Error('Failed to load consent modes');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Preferences
// ---------------------------------------------------------------------------

export async function fetchPreference(tenureId: number): Promise<SocialConsentPreference> {
  const res = await apiFetch(`/api/consent/preferences/for-tenure/${tenureId}/`);
  if (!res.ok) {
    throw new Error('Failed to load consent preference');
  }
  return res.json();
}

export async function updatePreference(
  id: number,
  body: Partial<SocialConsentPreferenceRequest>
): Promise<SocialConsentPreference> {
  const res = await apiFetch(`/api/consent/preferences/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to update consent preference');
  }
  return res.json();
}

export async function createPreference(
  body: SocialConsentPreferenceRequest
): Promise<SocialConsentPreference> {
  const res = await apiFetch('/api/consent/preferences/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to create consent preference');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Category rules
// ---------------------------------------------------------------------------

export async function fetchCategoryRules(preferenceId: number): Promise<PaginatedCategoryRules> {
  const res = await apiFetch(`/api/consent/category-rules/?preference=${preferenceId}`);
  if (!res.ok) {
    throw new Error('Failed to load consent category rules');
  }
  return res.json();
}

export async function upsertCategoryRule(
  body: SocialConsentCategoryRuleRequest
): Promise<SocialConsentCategoryRule> {
  const res = await apiFetch('/api/consent/category-rules/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to save consent category rule');
  }
  return res.json();
}

export async function deleteCategoryRule(id: number): Promise<void> {
  const res = await apiFetch(`/api/consent/category-rules/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to delete consent category rule');
  }
}

// ---------------------------------------------------------------------------
// Whitelist
// ---------------------------------------------------------------------------

export async function fetchWhitelist(
  tenureId: number,
  categoryId: number
): Promise<PaginatedWhitelist> {
  const params = new URLSearchParams({
    owner_tenure: String(tenureId),
    category: String(categoryId),
  });
  const res = await apiFetch(`/api/consent/whitelist/?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load consent whitelist');
  }
  return res.json();
}

export async function addWhitelist(
  body: SocialConsentWhitelistRequest
): Promise<SocialConsentWhitelist> {
  const res = await apiFetch('/api/consent/whitelist/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to add whitelist entry');
  }
  return res.json();
}

export async function removeWhitelist(id: number): Promise<void> {
  const res = await apiFetch(`/api/consent/whitelist/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to remove whitelist entry');
  }
}

// ---------------------------------------------------------------------------
// Blacklist (#1698 — antagonism blacklist, consulted under ALL_BUT_BLACKLIST)
// ---------------------------------------------------------------------------

export async function fetchBlacklist(
  tenureId: number,
  categoryId: number
): Promise<PaginatedBlacklist> {
  const params = new URLSearchParams({
    owner_tenure: String(tenureId),
    category: String(categoryId),
  });
  const res = await apiFetch(`/api/consent/blacklist/?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load consent blacklist');
  }
  return res.json();
}

export async function addBlacklist(
  body: SocialConsentBlacklistRequest
): Promise<SocialConsentBlacklist> {
  const res = await apiFetch('/api/consent/blacklist/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error('Failed to add blacklist entry');
  }
  return res.json();
}

export async function removeBlacklist(id: number): Promise<void> {
  const res = await apiFetch(`/api/consent/blacklist/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to remove blacklist entry');
  }
}
