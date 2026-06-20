import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { WhitelistManager } from './WhitelistManager';
import { useUpsertCategoryRule, useDeleteCategoryRule } from '../queries';
import type { SocialConsentCategory, SocialConsentCategoryRule } from '../types';

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
    } else if (value === 'allowlist') {
      upsertRule.mutate({ preference: preferenceId, category: category.id, mode: 'allowlist' });
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
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="everyone">Everyone</SelectItem>
            <SelectItem value="allowlist">Allowlist only</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {currentMode === 'allowlist' && (
        <WhitelistManager tenureId={tenureId} categoryId={category.id} />
      )}
    </div>
  );
}
