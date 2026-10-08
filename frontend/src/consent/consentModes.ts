import type {
  SocialConsentCategory,
  SocialConsentCategoryRule,
  SocialConsentCategoryRuleModeEnum,
} from './types';

/**
 * Consent-mode presentation + tree-inheritance resolution (#2170).
 *
 * Mirrors the backend `world.consent.services.effective_consent_mode`: a category with no
 * player rule inherits its parent's effective mode, walking up to the root's `default_mode`.
 * The frontend resolves the same walk-up client-side (over the loaded categories + rules) so
 * a row can show its *inherited* mode without an extra request.
 */

export type ConsentMode = SocialConsentCategoryRuleModeEnum;

/** Permissive → restrictive, matching the backend ConsentMode axis. */
export const MODE_ORDER: ConsentMode[] = [
  'everyone',
  'all_but_blacklist',
  'friends_whitelist',
  'rivals',
  'allowlist',
];

export const MODE_LABELS: Record<ConsentMode, string> = {
  everyone: 'Everyone',
  ask: 'Ask me each time',
  all_but_blacklist: 'Everyone except blacklist',
  friends_whitelist: 'Friends + whitelist',
  rivals: 'My declared rivals',
  allowlist: 'Allowlist only',
};

/**
 * A category that asks before acting (`asks_before_acting`, a makeover, #4187) offers
 * three plain choices in place of the social-action modes. They are the `ask`,
 * `everyone` and `allowlist` modes under names that say what they do to a deed that
 * waits for your answer; the whitelist skips the ask and the blacklist refuses either way.
 */
export const ASKING_MODE_ORDER: ConsentMode[] = ['ask', 'everyone', 'allowlist'];

export const ASKING_MODE_LABELS: Partial<Record<ConsentMode, string>> = {
  ask: 'Ask me',
  everyone: 'Always allow',
  allowlist: 'Never',
};

/** The picker label for `mode` on `category`: the asking names when the category asks. */
export function modeLabel(mode: ConsentMode, asksBeforeActing: boolean): string {
  return (asksBeforeActing ? ASKING_MODE_LABELS[mode] : undefined) ?? MODE_LABELS[mode];
}

/** Sentinel Select value for "no rule of my own — inherit from parent / root default". */
export const INHERIT_VALUE = 'inherit';

/** A row on the `GET /api/consent/categories/modes/` response (#2170). */
export interface ConsentModeGuidance {
  value: ConsentMode;
  label: string;
  guidance: string;
}

/**
 * The effective mode governing `categoryId` after tree inheritance: the nearest ancestor
 * (starting at the category) carrying a player rule wins; if none does, the root's
 * `default_mode`. Cycle-guarded so a mis-seeded loop can't hang the walk.
 */
export function resolveEffectiveMode(
  categoryId: number,
  categoriesById: Map<number, SocialConsentCategory>,
  ruleByCategoryId: Map<number, SocialConsentCategoryRule>
): ConsentMode {
  const seen = new Set<number>();
  let current: SocialConsentCategory | undefined = categoriesById.get(categoryId);
  let root: SocialConsentCategory | undefined = current;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    const rule = ruleByCategoryId.get(current.id);
    if (rule?.mode) {
      return rule.mode;
    }
    root = current;
    current = current.parent != null ? categoriesById.get(current.parent) : undefined;
  }
  return (root?.default_mode as ConsentMode | undefined) ?? 'everyone';
}
