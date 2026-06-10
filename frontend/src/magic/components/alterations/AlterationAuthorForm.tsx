/**
 * AlterationAuthorForm — author-from-scratch path of AlterationResolveDialog (#877).
 *
 * Wire contract: AlterationResolutionSerializer
 * (src/world/magic/serializers.py) + validate_alteration_resolution
 * (src/world/magic/services/alterations.py).
 *
 * Note: tier and origin are injected server-side from the pending alteration
 * and are never included in the client payload.
 */

import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useDamageTypes } from '@/conditions/queries';
import { MIN_ALTERATION_DESCRIPTION_LENGTH } from '../../types';
import type { AlterationScratchPayload, AlterationTierCaps, PendingAlteration } from '../../types';

export interface AlterationAuthorFormProps {
  pending: PendingAlteration;
  caps: AlterationTierCaps;
  fieldErrors: Record<string, string[]>;
  isPending: boolean;
  onSubmit: (payload: AlterationScratchPayload) => void;
}

/** Produce an array [0, 1, …, cap] for magnitude option rendering. */
function capRange(cap: number): number[] {
  return Array.from({ length: cap + 1 }, (_, i) => i);
}

export function AlterationAuthorForm({
  pending: _pending,
  caps,
  fieldErrors,
  isPending,
  onSubmit,
}: AlterationAuthorFormProps) {
  const [name, setName] = useState('');
  const [playerDescription, setPlayerDescription] = useState('');
  const [observerDescription, setObserverDescription] = useState('');
  const [weaknessMagnitude, setWeaknessMagnitude] = useState(0);
  const [weaknessDamageTypeId, setWeaknessDamageTypeId] = useState<number | null>(null);
  const [resonanceBonus, setResonanceBonus] = useState(0);
  const [socialReactivity, setSocialReactivity] = useState(0);
  const [visibleAtRest, setVisibleAtRest] = useState(caps.visibility_required);

  const { data: damageTypes = [] } = useDamageTypes();

  // Validation
  const trimmedName = name.trim();
  const nameValid = trimmedName.length >= 3 && trimmedName.length <= 60;
  const playerDescValid = playerDescription.length >= MIN_ALTERATION_DESCRIPTION_LENGTH;
  const observerDescValid = observerDescription.length >= MIN_ALTERATION_DESCRIPTION_LENGTH;
  const weaknessValid = weaknessMagnitude === 0 || weaknessDamageTypeId !== null;
  const canSubmit =
    nameValid && playerDescValid && observerDescValid && weaknessValid && !isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      name: trimmedName,
      player_description: playerDescription,
      observer_description: observerDescription,
      weakness_damage_type_id: weaknessMagnitude > 0 ? weaknessDamageTypeId : null,
      weakness_magnitude: weaknessMagnitude,
      resonance_bonus_magnitude: resonanceBonus,
      social_reactivity_magnitude: socialReactivity,
      is_visible_at_rest: caps.visibility_required ? true : visibleAtRest,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 pt-2">
      {/* Name */}
      <div className="space-y-1">
        <Label htmlFor="alteration-name">Name</Label>
        <Input
          id="alteration-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="3–60 characters"
          maxLength={60}
        />
        {fieldErrors.name?.map((err) => (
          <p key={err} className="text-xs text-destructive">
            {err}
          </p>
        ))}
      </div>

      {/* Player description */}
      <div className="space-y-1">
        <Label htmlFor="alteration-player-desc">How it feels to you</Label>
        <Textarea
          id="alteration-player-desc"
          value={playerDescription}
          onChange={(e) => setPlayerDescription(e.target.value)}
          placeholder="Describe how the alteration feels from your character's perspective…"
          rows={3}
        />
        <p className={`text-xs ${playerDescValid ? 'text-green-600' : 'text-muted-foreground'}`}>
          {playerDescription.length} / {MIN_ALTERATION_DESCRIPTION_LENGTH} minimum
        </p>
        {fieldErrors.player_description?.map((err) => (
          <p key={err} className="text-xs text-destructive">
            {err}
          </p>
        ))}
      </div>

      {/* Observer description */}
      <div className="space-y-1">
        <Label htmlFor="alteration-observer-desc">What others see</Label>
        <Textarea
          id="alteration-observer-desc"
          value={observerDescription}
          onChange={(e) => setObserverDescription(e.target.value)}
          placeholder="Describe what bystanders notice about this alteration…"
          rows={3}
        />
        <p className={`text-xs ${observerDescValid ? 'text-green-600' : 'text-muted-foreground'}`}>
          {observerDescription.length} / {MIN_ALTERATION_DESCRIPTION_LENGTH} minimum
        </p>
        {fieldErrors.observer_description?.map((err) => (
          <p key={err} className="text-xs text-destructive">
            {err}
          </p>
        ))}
      </div>

      {/* Weakness magnitude */}
      <div className="space-y-1">
        <Label htmlFor="alteration-weakness-mag">Weakness magnitude</Label>
        <select
          id="alteration-weakness-mag"
          value={weaknessMagnitude}
          onChange={(e) => {
            const val = Number(e.target.value);
            setWeaknessMagnitude(val);
            if (val === 0) setWeaknessDamageTypeId(null);
          }}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {capRange(caps.weakness_cap).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">max {caps.weakness_cap} for this tier</p>
      </div>

      {/* Weakness damage type — only enabled when weakness > 0 */}
      <div className="space-y-1">
        <Label htmlFor="alteration-weakness-type">Weakness damage type</Label>
        <select
          id="alteration-weakness-type"
          value={weaknessDamageTypeId ?? ''}
          disabled={weaknessMagnitude === 0}
          onChange={(e) => {
            const val = e.target.value;
            setWeaknessDamageTypeId(val === '' ? null : Number(val));
          }}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          <option value="">— select a type —</option>
          {damageTypes.map((dt) => (
            <option key={dt.id} value={dt.id}>
              {dt.name}
            </option>
          ))}
        </select>
      </div>

      {/* Resonance bonus */}
      <div className="space-y-1">
        <Label htmlFor="alteration-resonance-mag">Resonance bonus</Label>
        <select
          id="alteration-resonance-mag"
          value={resonanceBonus}
          onChange={(e) => setResonanceBonus(Number(e.target.value))}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {capRange(caps.resonance_cap).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">max {caps.resonance_cap} for this tier</p>
      </div>

      {/* Social reactivity */}
      <div className="space-y-1">
        <Label htmlFor="alteration-social-mag">Social reactivity</Label>
        <select
          id="alteration-social-mag"
          value={socialReactivity}
          onChange={(e) => setSocialReactivity(Number(e.target.value))}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {capRange(caps.social_cap).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">max {caps.social_cap} for this tier</p>
      </div>

      {/* Visible at rest */}
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <Switch
            id="alteration-visible-at-rest"
            checked={caps.visibility_required ? true : visibleAtRest}
            disabled={caps.visibility_required}
            onCheckedChange={caps.visibility_required ? undefined : setVisibleAtRest}
          />
          <Label htmlFor="alteration-visible-at-rest">Visible at rest</Label>
        </div>
        {caps.visibility_required && (
          <p className="text-xs text-muted-foreground">
            An alteration this profound cannot be hidden.
          </p>
        )}
      </div>

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={!canSubmit}>
          {isPending ? 'Binding…' : 'Bind this mark'}
        </Button>
      </div>
    </form>
  );
}
