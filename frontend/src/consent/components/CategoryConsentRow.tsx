import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { WhitelistManager } from './WhitelistManager';
import { BlacklistManager } from './BlacklistManager';
import { useUpsertCategoryRule, useDeleteCategoryRule } from '../queries';
import {
  INHERIT_VALUE,
  MODE_LABELS,
  MODE_ORDER,
  resolveEffectiveMode,
  type ConsentMode,
} from '../consentModes';
import type { SocialConsentCategory, SocialConsentCategoryRule } from '../types';

interface Props {
  tenureId: number;
  preferenceId: number;
  category: SocialConsentCategory;
  rule: SocialConsentCategoryRule | undefined;
  /** All categories keyed by id — used to resolve the inherited mode up the parent chain. */
  categoriesById: Map<number, SocialConsentCategory>;
  /** This player's rules keyed by category id — for the inheritance walk. */
  ruleByCategoryId: Map<number, SocialConsentCategoryRule>;
  /** ConsentMode value → pros/cons guidance copy (from the modes endpoint). */
  guidanceByMode: Map<string, string>;
  /** Nesting depth (0 = root) — drives the left indent of a child row. */
  depth: number;
}

export function CategoryConsentRow({
  tenureId,
  preferenceId,
  category,
  rule,
  categoriesById,
  ruleByCategoryId,
  guidanceByMode,
  depth,
}: Props) {
  const upsertRule = useUpsertCategoryRule();
  const deleteRule = useDeleteCategoryRule();

  // No rule of my own = inherit from the parent chain (the Select shows "Inherit …").
  const selectValue: string = rule?.mode ?? INHERIT_VALUE;
  // The mode that actually governs this category right now — the explicit rule, or the
  // resolved inherited mode. Drives which manager (whitelist/blacklist) to show + the copy.
  const effectiveMode: ConsentMode =
    rule?.mode ?? resolveEffectiveMode(category.id, categoriesById, ruleByCategoryId);
  const isRoot = category.parent == null;

  function handleModeChange(value: string) {
    if (value === INHERIT_VALUE) {
      if (rule?.id) {
        deleteRule.mutate({ id: rule.id, preferenceId });
      }
      // No rule yet → already inheriting; nothing to do.
    } else {
      upsertRule.mutate({
        preference: preferenceId,
        category: category.id,
        mode: value as ConsentMode,
      });
    }
  }

  // A root category has no parent to inherit from — "Inherit" would just mean its own
  // default, so offer "Everyone" as the open option instead of an Inherit sentinel.
  const inheritOptionLabel = isRoot
    ? `Default (${MODE_LABELS[effectiveMode]})`
    : `Inherit from parent (${MODE_LABELS[effectiveMode]})`;

  return (
    <div className="space-y-2" style={{ marginLeft: depth * 20 }}>
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5">
          <p className="font-medium">{category.name}</p>
          {category.description ? (
            <p className="text-sm text-muted-foreground">{category.description}</p>
          ) : null}
          {rule == null && !isRoot ? (
            <p className="text-xs italic text-muted-foreground">
              Inheriting {MODE_LABELS[effectiveMode]} from “{parentName(category, categoriesById)}”.
            </p>
          ) : null}
        </div>
        <Select
          value={selectValue}
          onValueChange={handleModeChange}
          disabled={upsertRule.isPending || deleteRule.isPending}
        >
          <SelectTrigger className="w-64 shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={INHERIT_VALUE}>{inheritOptionLabel}</SelectItem>
            {MODE_ORDER.map((mode) => (
              <SelectItem key={mode} value={mode}>
                {MODE_LABELS[mode]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {guidanceByMode.get(effectiveMode) ? (
        <p className="text-xs text-muted-foreground">{guidanceByMode.get(effectiveMode)}</p>
      ) : null}
      {/* Allowlist / friends / rivals all consult the whitelist (friends & mutual rivals
          auto-pass); all-but-blacklist consults the blacklist. Keyed off the EFFECTIVE mode
          so an inherited allowlist still surfaces its whitelist manager. */}
      {(effectiveMode === 'allowlist' ||
        effectiveMode === 'friends_whitelist' ||
        effectiveMode === 'rivals') && (
        <WhitelistManager tenureId={tenureId} categoryId={category.id} />
      )}
      {effectiveMode === 'all_but_blacklist' && (
        <BlacklistManager tenureId={tenureId} categoryId={category.id} />
      )}
    </div>
  );
}

function parentName(
  category: SocialConsentCategory,
  categoriesById: Map<number, SocialConsentCategory>
): string {
  const parent = category.parent != null ? categoriesById.get(category.parent) : undefined;
  return parent?.name ?? 'default';
}
