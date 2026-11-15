/**
 * FuryDeclaration — "Surrender control": tier + resonance pickers for a combat
 * cast (#1543, #4738, #5124). Each tier is a preset amount of control surrendered; the preview
 * reads the most intensity the server says that tier can buy at the resonance's strength.
 * Shown by YourTurn only when the focused slot is a cast. Holds no state (state
 * lives in YourTurn, threaded via callbacks — mirrors selectedPull/strainByClash).
 * When both are cleared, YourTurn sends no fury kwargs.
 */
import type { FuryTierOption, FuryResonanceOption } from '@/scenes/actionTypes';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

function furyTierLabel(tier: FuryTierOption): string {
  const label = `${tier.name}: surrender ${tier.control_surrendered} control`;
  return tier.is_berserk ? `${label} (Berserk)` : label;
}

function fullIntensityFor(tier: FuryTierOption, resonance: FuryResonanceOption): number {
  const scaled = resonance.tier_full_intensities.find((row) => row.tier_id === tier.id);
  return scaled?.full_intensity ?? tier.full_intensity;
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
  const selectedTier = tiers.find((t) => t.id === tierId) ?? null;
  const selectedResonance = resonances.find((r) => r.id === resonanceId) ?? null;
  const overCap =
    selectedTier !== null &&
    selectedResonance !== null &&
    selectedTier.depth > selectedResonance.provocation_cap;

  return (
    <div
      className="space-y-2 rounded border border-border bg-card/60 p-2"
      data-testid="fury-declaration"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Surrender control
      </p>
      <div className="space-y-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Tier</span>
        <Select
          value={tierId !== null ? String(tierId) : ''}
          onValueChange={(v) => onTierChange(v === '' ? null : Number(v))}
          disabled={disabled}
        >
          <SelectTrigger data-testid="fury-tier-select" className="h-8 text-xs">
            <SelectValue placeholder="No fury" />
          </SelectTrigger>
          <SelectContent>
            {tiers.map((t) => (
              <SelectItem key={t.id} value={String(t.id)} className="text-xs">
                {furyTierLabel(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Resonance</span>
        <Select
          value={resonanceId !== null ? String(resonanceId) : ''}
          onValueChange={(v) => onResonanceChange(v === '' ? null : Number(v))}
          disabled={disabled || tierId === null}
        >
          <SelectTrigger data-testid="fury-resonance-select" className="h-8 text-xs">
            <SelectValue placeholder="Resonance to give in to" />
          </SelectTrigger>
          <SelectContent>
            {resonances.map((r) => (
              <SelectItem key={r.id} value={String(r.id)} className="text-xs">
                {r.name} (cap {r.provocation_cap})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selectedTier !== null && selectedResonance !== null && (
        <p className="text-xs tabular-nums text-foreground" data-testid="fury-preview">
          {selectedTier.control_surrendered} control → up to +
          {fullIntensityFor(selectedTier, selectedResonance)} intensity, by your roll
        </p>
      )}
      {overCap && (
        <p className="text-[10px] text-destructive" data-testid="fury-over-cap-warning">
          Fury tier is deeper than {selectedResonance?.name} lets you go.
        </p>
      )}
    </div>
  );
}
