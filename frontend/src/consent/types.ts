import type { components } from '@/generated/api';

export type SocialConsentCategory = components['schemas']['SocialConsentCategory'];
export type SocialConsentPreference = components['schemas']['SocialConsentPreference'];
export type SocialConsentPreferenceRequest =
  components['schemas']['SocialConsentPreferenceRequest'];
export type SocialConsentCategoryRule = components['schemas']['SocialConsentCategoryRule'];
export type SocialConsentCategoryRuleRequest =
  components['schemas']['SocialConsentCategoryRuleRequest'];
// ConsentMode is one shared enum (pinned `ConsentModeEnum`, #2170) used by both the rule
// `mode` and the category `default_mode`.
export type SocialConsentCategoryRuleModeEnum = components['schemas']['ConsentModeEnum'];
export type SocialConsentWhitelist = components['schemas']['SocialConsentWhitelist'];
export type SocialConsentWhitelistRequest = components['schemas']['SocialConsentWhitelistRequest'];
export type SocialConsentBlacklist = components['schemas']['SocialConsentBlacklist'];
export type SocialConsentBlacklistRequest = components['schemas']['SocialConsentBlacklistRequest'];
export type PaginatedSocialConsentCategoryList =
  components['schemas']['PaginatedSocialConsentCategoryList'];
export type PaginatedSocialConsentCategoryRuleList =
  components['schemas']['PaginatedSocialConsentCategoryRuleList'];
export type PaginatedSocialConsentWhitelistList =
  components['schemas']['PaginatedSocialConsentWhitelistList'];
export type PaginatedSocialConsentBlacklistList =
  components['schemas']['PaginatedSocialConsentBlacklistList'];
