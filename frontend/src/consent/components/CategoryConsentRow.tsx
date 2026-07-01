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
import type {
  SocialConsentCategory,
  SocialConsentCategoryRule,
  SocialConsentCategoryRuleModeEnum,
} from '../types';

interface Props {
  tenureId: number;
  preferenceId: number;
  category: SocialConsentCategory;
  rule: SocialConsentCategoryRule | undefined;
}

export function CategoryConsentRow({ tenureId, preferenceId, category, rule }: Props) {
  const upsertRule = useUpsertCategoryRule();
  const deleteRule = useDeleteCategoryRule();

  const currentMode = rule?.mode ?? 'everyone';

  function handleModeChange(value: string) {
    if (value === 'everyone') {
      if (rule?.id) {
        deleteRule.mutate({ id: rule.id, preferenceId });
      }
      // If there's no rule yet "everyone" is the implicit default — nothing to do.
    } else {
      // allowlist / all_but_blacklist / friends_whitelist all upsert the mode (#1698).
      upsertRule.mutate({
        preference: preferenceId,
        category: category.id,
        mode: value as SocialConsentCategoryRuleModeEnum,
      });
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <p className="font-medium">{category.name}</p>
          {category.description ? (
            <p className="text-sm text-muted-foreground">{category.description}</p>
          ) : null}
        </div>
        <Select
          value={currentMode}
          onValueChange={handleModeChange}
          disabled={upsertRule.isPending || deleteRule.isPending}
        >
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="everyone">Everyone</SelectItem>
            <SelectItem value="all_but_blacklist">Everyone except blacklist</SelectItem>
            <SelectItem value="friends_whitelist">Friends + whitelist</SelectItem>
            <SelectItem value="allowlist">Allowlist only</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {/* Allowlist and friends-whitelist both consult the whitelist (friends auto-pass);
          all-but-blacklist consults the blacklist. */}
      {(currentMode === 'allowlist' || currentMode === 'friends_whitelist') && (
        <WhitelistManager tenureId={tenureId} categoryId={category.id} />
      )}
      {currentMode === 'all_but_blacklist' && (
        <BlacklistManager tenureId={tenureId} categoryId={category.id} />
      )}
    </div>
  );
}
