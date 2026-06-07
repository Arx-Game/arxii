/**
 * TechniqueBuilderForm — staff/player form for authoring a technique.
 *
 * - mode='staff': budget meter is advisory; submit is never blocked by budget.
 * - mode='player': submit is disabled when the design exceeds tier budget.
 *
 * A debounced call to usePriceTechnique drives the live budget meter.
 * Submitting calls useAuthorTechnique.
 *
 * Payload row editors (capability_grants, damage_profiles, applied_conditions)
 * live in TechniquePayloadEditors.tsx to keep this file focused.
 */

import { useState, useEffect, useRef } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { usePriceTechnique, useAuthorTechnique } from '../queries';
import type { TechniqueCostBreakdown } from '../types';
import {
  CapabilityGrantsEditor,
  DamageProfilesEditor,
  AppliedConditionsEditor,
} from './TechniquePayloadEditors';
import type {
  CapabilityGrantRow,
  CapabilityType,
  DamageProfileRow,
  DamageType,
  AppliedConditionRow,
} from './TechniquePayloadEditors';

// ---------------------------------------------------------------------------
// Types for lookup lists passed in from the page
// ---------------------------------------------------------------------------

interface GiftOption {
  id: number;
  name: string;
}

interface StyleOption {
  id: number;
  name: string;
}

interface EffectTypeOption {
  id: number;
  name: string;
}

interface ConditionOption {
  id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TechniqueBuilderFormProps {
  mode: 'staff' | 'player';
  gifts: GiftOption[];
  styles: StyleOption[];
  effectTypes: EffectTypeOption[];
  capabilities: CapabilityType[];
  damageTypes: DamageType[];
  conditions: ConditionOption[];
  characterId?: number;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACTION_CATEGORIES = [
  { value: 'physical', label: 'Physical' },
  { value: 'social', label: 'Social' },
  { value: 'mental', label: 'Mental' },
] as const;

const TIER_OPTIONS = [1, 2, 3, 4, 5] as const;

const DEBOUNCE_MS = 500;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'An unexpected error occurred.';
}

// ---------------------------------------------------------------------------
// Budget Meter
// ---------------------------------------------------------------------------

interface BudgetMeterProps {
  breakdown: TechniqueCostBreakdown | null;
  mode: 'staff' | 'player';
}

function BudgetMeter({ breakdown, mode }: BudgetMeterProps) {
  if (!breakdown) {
    return (
      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">
          Fill in the form above to see the cost breakdown.
        </p>
      </div>
    );
  }

  const pct = breakdown.budget > 0 ? (breakdown.total_cost / breakdown.budget) * 100 : 0;
  const overBudget = !breakdown.within_budget;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span>
          Cost:{' '}
          <strong>
            {breakdown.total_cost} / {breakdown.budget}
          </strong>{' '}
          (Tier {breakdown.tier})
        </span>
        {overBudget ? (
          <Badge variant={mode === 'player' ? 'destructive' : 'secondary'}>Over budget</Badge>
        ) : (
          <Badge variant="outline" className="border-green-600 text-green-700">
            Within budget
          </Badge>
        )}
      </div>
      <Progress value={Math.min(pct, 100)} className={overBudget ? 'bg-destructive/20' : ''} />
      {breakdown.lines.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
          {breakdown.lines.map((line) => (
            <li key={line.dimension} className="flex justify-between">
              <span>{line.label}</span>
              <span>{line.power_cost} pts</span>
            </li>
          ))}
          {breakdown.refund > 0 && (
            <li className="flex justify-between text-green-700">
              <span>Restriction refund</span>
              <span>−{breakdown.refund} pts</span>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main form component
// ---------------------------------------------------------------------------

export function TechniqueBuilderForm({
  mode,
  gifts,
  styles,
  effectTypes,
  capabilities,
  damageTypes,
  conditions,
  characterId,
  onSuccess,
}: TechniqueBuilderFormProps) {
  // Core fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [giftId, setGiftId] = useState<number | null>(gifts[0]?.id ?? null);
  const [styleId, setStyleId] = useState<number | null>(styles[0]?.id ?? null);
  const [effectTypeId, setEffectTypeId] = useState<number | null>(effectTypes[0]?.id ?? null);
  const [actionCategory, setActionCategory] = useState<string>('physical');
  const [tier, setTier] = useState<number>(1);
  const [intensity, setIntensity] = useState<number>(1);
  const [control, setControl] = useState<number>(1);
  const [animaCost, setAnimaCost] = useState<number>(1);

  // Payload rows
  const [capabilityGrants, setCapabilityGrants] = useState<CapabilityGrantRow[]>([]);
  const [damageProfiles, setDamageProfiles] = useState<DamageProfileRow[]>([]);
  const [appliedConditions, setAppliedConditions] = useState<AppliedConditionRow[]>([]);

  // Budget meter state
  const [breakdown, setBreakdown] = useState<TechniqueCostBreakdown | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mutations
  const priceMutation = usePriceTechnique();
  const authorMutation = useAuthorTechnique();

  // ---------------------------------------------------------------------------
  // Live pricing — debounced on form field changes
  // ---------------------------------------------------------------------------

  const canPrice =
    name.trim() !== '' && giftId !== null && styleId !== null && effectTypeId !== null;

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!canPrice) {
      setBreakdown(null);
      return;
    }
    debounceRef.current = setTimeout(() => {
      priceMutation.mutate(
        {
          name: name.trim(),
          description,
          gift_id: giftId!,
          style_id: styleId!,
          effect_type_id: effectTypeId!,
          action_category: actionCategory,
          tier,
          intensity,
          control,
          anima_cost: animaCost,
          capability_grants: capabilityGrants.map((r) => ({
            capability_id: r.capability_id,
            base_value: r.base_value,
            intensity_multiplier: r.intensity_multiplier,
          })),
          damage_profiles: damageProfiles.map((r) => ({
            damage_type_id: r.damage_type_id,
            base_damage: r.base_damage,
            damage_intensity_multiplier: r.damage_intensity_multiplier,
          })),
          applied_conditions: appliedConditions.map((r) => ({
            condition_id: r.condition_id,
            base_severity: r.base_severity,
            base_duration_rounds: r.base_duration_rounds,
          })),
          character_id: characterId,
        },
        {
          onSuccess: (data) => setBreakdown(data),
          onError: () => setBreakdown(null),
        }
      );
    }, DEBOUNCE_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    name,
    description,
    giftId,
    styleId,
    effectTypeId,
    actionCategory,
    tier,
    intensity,
    control,
    animaCost,
    capabilityGrants,
    damageProfiles,
    appliedConditions,
  ]);

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  const overBudget = breakdown !== null && !breakdown.within_budget;
  const submitDisabled = !canPrice || authorMutation.isPending || (mode === 'player' && overBudget);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitDisabled || giftId === null || styleId === null || effectTypeId === null) return;

    authorMutation.mutate(
      {
        name: name.trim(),
        description,
        gift_id: giftId,
        style_id: styleId,
        effect_type_id: effectTypeId,
        action_category: actionCategory,
        tier,
        intensity,
        control,
        anima_cost: animaCost,
        capability_grants: capabilityGrants,
        damage_profiles: damageProfiles,
        applied_conditions: appliedConditions,
        character_id: characterId,
      },
      {
        onSuccess: () => {
          onSuccess?.();
        },
      }
    );
  }

  const isPending = authorMutation.isPending;
  const errorMessage = authorMutation.isError ? extractErrorMessage(authorMutation.error) : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Core fields                                                          */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Technique Details</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {/* Name */}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="tech-name">Name *</Label>
            <Input
              id="tech-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Veilstep"
              disabled={isPending}
              required
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="tech-desc">Description</Label>
            <Textarea
              id="tech-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this technique does…"
              rows={3}
              disabled={isPending}
            />
          </div>

          {/* Gift */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-gift">Gift *</Label>
            <Select
              value={giftId != null ? String(giftId) : ''}
              onValueChange={(val) => setGiftId(Number(val))}
              disabled={isPending}
            >
              <SelectTrigger id="tech-gift">
                <SelectValue placeholder="Select a gift" />
              </SelectTrigger>
              <SelectContent>
                {gifts.map((g) => (
                  <SelectItem key={g.id} value={String(g.id)}>
                    {g.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Style */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-style">Style *</Label>
            <Select
              value={styleId != null ? String(styleId) : ''}
              onValueChange={(val) => setStyleId(Number(val))}
              disabled={isPending}
            >
              <SelectTrigger id="tech-style">
                <SelectValue placeholder="Select a style" />
              </SelectTrigger>
              <SelectContent>
                {styles.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Effect Type */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-effect">Effect Type *</Label>
            <Select
              value={effectTypeId != null ? String(effectTypeId) : ''}
              onValueChange={(val) => setEffectTypeId(Number(val))}
              disabled={isPending}
            >
              <SelectTrigger id="tech-effect">
                <SelectValue placeholder="Select effect type" />
              </SelectTrigger>
              <SelectContent>
                {effectTypes.map((et) => (
                  <SelectItem key={et.id} value={String(et.id)}>
                    {et.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Action Category */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-action-cat">Action Category *</Label>
            <Select value={actionCategory} onValueChange={setActionCategory} disabled={isPending}>
              <SelectTrigger id="tech-action-cat">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACTION_CATEGORIES.map((ac) => (
                  <SelectItem key={ac.value} value={ac.value}>
                    {ac.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Tier */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-tier">Tier</Label>
            <Select
              value={String(tier)}
              onValueChange={(val) => setTier(Number(val))}
              disabled={isPending}
            >
              <SelectTrigger id="tech-tier">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIER_OPTIONS.map((t) => (
                  <SelectItem key={t} value={String(t)}>
                    Tier {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Intensity */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-intensity">Intensity</Label>
            <Input
              id="tech-intensity"
              type="number"
              min={0}
              value={intensity}
              onChange={(e) => setIntensity(Number(e.target.value))}
              disabled={isPending}
            />
          </div>

          {/* Control */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-control">Control</Label>
            <Input
              id="tech-control"
              type="number"
              min={0}
              value={control}
              onChange={(e) => setControl(Number(e.target.value))}
              disabled={isPending}
            />
          </div>

          {/* Anima Cost */}
          <div className="space-y-1.5">
            <Label htmlFor="tech-anima">Anima Cost</Label>
            <Input
              id="tech-anima"
              type="number"
              min={0}
              value={animaCost}
              onChange={(e) => setAnimaCost(Number(e.target.value))}
              disabled={isPending}
            />
          </div>
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ */}
      {/* Payload rows                                                         */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Payloads</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <CapabilityGrantsEditor
            rows={capabilityGrants}
            capabilities={capabilities}
            disabled={isPending}
            onChange={setCapabilityGrants}
          />
          <Separator />
          <DamageProfilesEditor
            rows={damageProfiles}
            damageTypes={damageTypes}
            disabled={isPending}
            onChange={setDamageProfiles}
          />
          <Separator />
          <AppliedConditionsEditor
            rows={appliedConditions}
            conditions={conditions}
            disabled={isPending}
            onChange={setAppliedConditions}
          />
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ */}
      {/* Budget meter                                                         */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Budget</CardTitle>
        </CardHeader>
        <CardContent>
          <BudgetMeter breakdown={breakdown} mode={mode} />
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ */}
      {/* Error banner + submit                                                */}
      {/* ------------------------------------------------------------------ */}
      {errorMessage && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <p>{errorMessage}</p>
        </div>
      )}

      <div className="flex justify-end gap-3">
        <Button type="submit" disabled={submitDisabled}>
          {isPending ? 'Authoring…' : 'Author Technique'}
        </Button>
      </div>
    </form>
  );
}
