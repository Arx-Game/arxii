/**
 * FuryDeclaration — "Give in to your <resonance>": the kindled resonance picker and how far to
 * give in (#1543, #4738, #5124). Only kindled resonances are offered, each with its strength
 * word; the steps are Hold steady plus every tier its strength reaches, named as staff authored
 * them. Shown by YourTurn only when the focused slot is a cast. Holds no state (state lives in
 * YourTurn, threaded via callbacks — mirrors selectedPull/strainByClash). Hold steady or no
 * resonance sends no fury kwargs.
 */
import type { FuryTierOption, FuryResonanceOption } from '@/scenes/actionTypes';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

function fullIntensityFor(tier: FuryTierOption, resonance: FuryResonanceOption): number {
  const scaled = resonance.tier_full_intensities.find((row) => row.tier_id === tier.id);
  return scaled?.full_intensity ?? tier.full_intensity;
}

function strengthWord(resonance: FuryResonanceOption): string {
  return resonance.strength_name.toLowerCase();
}

interface FuryDeclarationProps {
  tiers: FuryTierOption[];
  resonances: FuryResonanceOption[];
  tierId: number | null;
  resonanceId: number | null;
  onTierChange: (id: number | null) => void;
  onResonanceChange: (id: number | null) => void;
  disabled?: boolean;
}

export function FuryDeclaration({
  tiers,
  resonances,
  tierId,
  resonanceId,
  onTierChange,
  onResonanceChange,
  disabled = false,
}: FuryDeclarationProps) {
  const selectedResonance = resonances.find((r) => r.id === resonanceId) ?? null;
  const reachable = [...tiers]
    .filter((t) => selectedResonance !== null && t.depth <= selectedResonance.provocation_cap)
    .sort((a, b) => a.depth - b.depth);
  const deepest = reachable.length > 0 ? reachable[reachable.length - 1] : null;
  const selectedTier = reachable.find((t) => t.id === tierId) ?? null;

  const chooseResonance = (value: string) => {
    const next = value === '' ? null : Number(value);
    onResonanceChange(next);
    // A step the new resonance does not reach is dropped back to Hold steady.
    const nextResonance = resonances.find((r) => r.id === next) ?? null;
    const held = tiers.find((t) => t.id === tierId) ?? null;
    if (held !== null && (nextResonance === null || held.depth > nextResonance.provocation_cap)) {
      onTierChange(null);
    }
  };

  return (
    <div
      className="space-y-2 rounded border border-border bg-card/60 p-2"
      data-testid="fury-declaration"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {selectedResonance !== null ? `Give in to your ${selectedResonance.name}` : 'Give in'}
      </p>
      <Select
        value={resonanceId !== null ? String(resonanceId) : ''}
        onValueChange={chooseResonance}
        disabled={disabled}
      >
        <SelectTrigger data-testid="fury-resonance-select" className="h-8 text-xs">
          <SelectValue placeholder="Choose a kindled resonance" />
        </SelectTrigger>
        <SelectContent>
          {resonances.map((r) => (
            <SelectItem key={r.id} value={String(r.id)} className="text-xs">
              {r.name} (kindled, {strengthWord(r)})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selectedResonance !== null && (
        <>
          <div className="flex flex-wrap gap-1" role="group" aria-label="How far to give in">
            <Button
              type="button"
              size="sm"
              variant={selectedTier === null ? 'default' : 'outline'}
              aria-pressed={selectedTier === null}
              data-testid="fury-tier-hold"
              onClick={() => onTierChange(null)}
              disabled={disabled}
            >
              Hold steady
            </Button>
            {reachable.map((t) => (
              <Button
                key={t.id}
                type="button"
                size="sm"
                variant={selectedTier?.id === t.id ? 'default' : 'outline'}
                aria-pressed={selectedTier?.id === t.id}
                data-testid={`fury-tier-${t.id}`}
                onClick={() => onTierChange(t.id)}
                disabled={disabled}
              >
                {t.name}
              </Button>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground" data-testid="fury-depth-line">
            Your {selectedResonance.name} is {strengthWord(selectedResonance)}
            {deepest !== null ? `: you can go as far as ${deepest.name}.` : '.'}
          </p>
        </>
      )}
      {selectedTier !== null && selectedResonance !== null && (
        <p className="text-xs tabular-nums text-foreground" data-testid="fury-preview">
          Give up {selectedTier.control_surrendered} control · Gain up to{' '}
          {fullIntensityFor(selectedTier, selectedResonance)} intensity, by your roll
        </p>
      )}
    </div>
  );
}
