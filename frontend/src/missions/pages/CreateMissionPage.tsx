/**
 * Mission Studio — create-from-scratch page.
 *
 * Full-page form at /staff/missions/new. Collects all template-level
 * fields (categories included). On submit, POSTs to /api/missions/
 * templates/ and navigates to the canvas with the new id so the
 * author can start adding nodes. Auto-suffix on name collision is
 * handled server-side; the saved name comes back in the response
 * and a toast surfaces any rename.
 *
 * availability_rule defaults to {} (predicate authoring is handled
 * by the existing PredicateBuilder on the detail surface).
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import { CategoryMultiSelect } from '../components/CategoryMultiSelect';
import { useCreateMissionTemplate } from '../queries';
import { ApiValidationError } from '../api';
import type { ArcScope, AccessTier } from '../types';
import type { components } from '@/generated/api';

type RewardGroupRule = components['schemas']['RewardGroupRuleEnum'];

type CooldownUnit = 'hours' | 'days' | 'weeks';

const ARC_SCOPES: { value: ArcScope; label: string }[] = [
  { value: 'global', label: 'Global' },
  { value: 'org', label: 'Org' },
  { value: 'giver', label: 'Giver' },
];

const REWARD_RULES: { value: RewardGroupRule; label: string }[] = [
  { value: 'all_equal', label: 'All equal' },
  { value: 'by_role', label: 'By role' },
  { value: 'by_participation', label: 'By participation' },
];

const ACCESS_TIERS: { value: AccessTier; label: string }[] = [
  { value: 'staff_only', label: 'Staff only (draft)' },
  { value: 'open', label: 'Open' },
];

function cooldownToISO(amount: number, unit: CooldownUnit): string {
  if (unit === 'hours') return `PT${amount}H`;
  if (unit === 'weeks') return `P${amount * 7}D`;
  return `P${amount}D`;
}

export function CreateMissionPage() {
  const navigate = useNavigate();
  const create = useCreateMissionTemplate();

  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [epilogue, setEpilogue] = useState('');
  const [levelMin, setLevelMin] = useState(1);
  const [levelMax, setLevelMax] = useState(5);
  const [riskTier, setRiskTier] = useState(1);
  const [baseWeight, setBaseWeight] = useState(1);
  const [arcScope, setArcScope] = useState<ArcScope>('global');
  const [percentReplace, setPercentReplace] = useState(0);
  const [cooldownAmount, setCooldownAmount] = useState(1);
  const [cooldownUnit, setCooldownUnit] = useState<CooldownUnit>('days');
  const [rewardRule, setRewardRule] = useState<RewardGroupRule>('all_equal');
  const [accessTier, setAccessTier] = useState<AccessTier>('staff_only');
  const [categories, setCategories] = useState<number[]>([]);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState<string | null>(null);

  const onSubmit = async () => {
    setFieldErrors({});
    setLocalError(null);

    if (levelMin > levelMax) {
      setLocalError('Level band min cannot exceed max.');
      return;
    }
    if (cooldownAmount <= 0) {
      setLocalError('Cooldown must be a positive number.');
      return;
    }

    const submittedName = name;
    try {
      const created = await create.mutateAsync({
        name,
        summary,
        epilogue,
        level_band_min: levelMin,
        level_band_max: levelMax,
        risk_tier: riskTier,
        base_weight: baseWeight,
        arc_scope: arcScope,
        percent_replace: percentReplace,
        cooldown: cooldownToISO(cooldownAmount, cooldownUnit),
        reward_group_rule: rewardRule,
        access_tier: accessTier,
        categories,
      });
      if (created.name !== submittedName) {
        toast.success(`Saved as "${created.name}" — "${submittedName}" was taken.`);
      }
      navigate(`/staff/missions/${created.id}/canvas`);
    } catch (err) {
      if (err instanceof ApiValidationError) {
        const flat: Record<string, string> = {};
        for (const [key, msgs] of Object.entries(err.fieldErrors)) {
          flat[key] = Array.isArray(msgs) ? msgs[0] : String(msgs);
        }
        setFieldErrors(flat);
      } else {
        setLocalError('Could not create mission.');
      }
    }
  };

  return (
    <div className="container mx-auto max-w-3xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">New Mission</h1>
        <Button variant="outline" onClick={() => navigate('/staff/missions')}>
          ← Back
        </Button>
      </div>
      {localError ? (
        <div className="mb-3 rounded border border-destructive bg-destructive/10 p-2 text-sm">
          {localError}
        </div>
      ) : null}
      <div className="space-y-4">
        <FormRow label="Name" error={fieldErrors.name} required>
          <Input id="field-name" value={name} onChange={(e) => setName(e.target.value)} />
        </FormRow>
        <FormRow label="Summary" error={fieldErrors.summary} required>
          <Textarea
            id="field-summary"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
        </FormRow>
        <FormRow label="Epilogue" error={fieldErrors.epilogue}>
          <Textarea
            id="field-epilogue"
            value={epilogue}
            onChange={(e) => setEpilogue(e.target.value)}
          />
        </FormRow>
        <div className="grid grid-cols-2 gap-3">
          <FormRow label="Level band min" error={fieldErrors.level_band_min} required>
            <Input
              id="field-level-band-min"
              type="number"
              value={levelMin}
              onChange={(e) => setLevelMin(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Level band max" error={fieldErrors.level_band_max} required>
            <Input
              id="field-level-band-max"
              type="number"
              value={levelMax}
              onChange={(e) => setLevelMax(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Risk tier" error={fieldErrors.risk_tier} required>
            <Input
              id="field-risk-tier"
              type="number"
              value={riskTier}
              onChange={(e) => setRiskTier(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Base weight" error={fieldErrors.base_weight}>
            <Input
              id="field-base-weight"
              type="number"
              value={baseWeight}
              onChange={(e) => setBaseWeight(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Arc scope" error={fieldErrors.arc_scope} required>
            <Select value={arcScope} onValueChange={(v) => setArcScope(v as ArcScope)}>
              <SelectTrigger id="field-arc-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ARC_SCOPES.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormRow>
          <FormRow label="% replace" error={fieldErrors.percent_replace}>
            <Input
              id="field-percent-replace"
              type="number"
              value={percentReplace}
              onChange={(e) => setPercentReplace(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Cooldown amount" error={fieldErrors.cooldown} required>
            <Input
              id="field-cooldown-amount"
              type="number"
              value={cooldownAmount}
              onChange={(e) => setCooldownAmount(Number(e.target.value))}
            />
          </FormRow>
          <FormRow label="Cooldown unit">
            <Select value={cooldownUnit} onValueChange={(v) => setCooldownUnit(v as CooldownUnit)}>
              <SelectTrigger id="field-cooldown-unit">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hours">Hours</SelectItem>
                <SelectItem value="days">Days</SelectItem>
                <SelectItem value="weeks">Weeks</SelectItem>
              </SelectContent>
            </Select>
          </FormRow>
          <FormRow label="Reward rule" error={fieldErrors.reward_group_rule}>
            <Select value={rewardRule} onValueChange={(v) => setRewardRule(v as RewardGroupRule)}>
              <SelectTrigger id="field-reward-rule">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REWARD_RULES.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormRow>
          <FormRow label="Access tier" error={fieldErrors.access_tier}>
            <Select value={accessTier} onValueChange={(v) => setAccessTier(v as AccessTier)}>
              <SelectTrigger id="field-access-tier">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACCESS_TIERS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormRow>
        </div>
        <div>
          <Label className="mb-1 block">Categories</Label>
          <CategoryMultiSelect value={categories} onChange={setCategories} />
          {fieldErrors.categories ? (
            <p className="mt-1 text-xs text-destructive">{fieldErrors.categories}</p>
          ) : null}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => navigate('/staff/missions')}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={create.isPending}>
            Create Mission
          </Button>
        </div>
      </div>
    </div>
  );
}

function FormRow({
  label,
  error,
  required,
  children,
}: {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  // Generate a stable id from the label text for htmlFor/id association
  const fieldId = label.replace(/\s+/g, '-').toLowerCase();
  return (
    <div>
      <Label htmlFor={`field-${fieldId}`}>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <div className="mt-1">{children}</div>
      {error ? <p className="mt-1 text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
