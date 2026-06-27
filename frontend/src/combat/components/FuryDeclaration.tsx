/**
 * FuryDeclaration — tier + bonded-anchor pickers for a combat cast (#1543).
 * Shown by YourTurn only when the focused slot is a cast. Holds no state (state
 * lives in YourTurn, threaded via callbacks — mirrors selectedPull/strainByClash).
 * When both are cleared, YourTurn sends no fury kwargs.
 */
import type { FuryTierOption, FuryAnchorOption } from '@/scenes/actionTypes';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface FuryDeclarationProps {
  tiers: FuryTierOption[];
  anchors: FuryAnchorOption[];
  tierId: number | null;
  anchorId: number | null;
  onTierChange: (id: number | null) => void;
  onAnchorChange: (id: number | null) => void;
  disabled?: boolean;
}

export function FuryDeclaration({
  tiers,
  anchors,
  tierId,
  anchorId,
  onTierChange,
  onAnchorChange,
  disabled = false,
}: FuryDeclarationProps) {
  const selectedTier = tiers.find((t) => t.id === tierId) ?? null;
  const selectedAnchor = anchors.find((a) => a.id === anchorId) ?? null;
  const overCap =
    selectedTier !== null &&
    selectedAnchor !== null &&
    selectedTier.depth > selectedAnchor.provocation_cap;

  return (
    <div
      className="space-y-2 rounded border border-border bg-card/60 p-2"
      data-testid="fury-declaration"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Fury</p>
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
                {t.name} (depth {t.depth})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Anchor</span>
        <Select
          value={anchorId !== null ? String(anchorId) : ''}
          onValueChange={(v) => onAnchorChange(v === '' ? null : Number(v))}
          disabled={disabled || tierId === null}
        >
          <SelectTrigger data-testid="fury-anchor-select" className="h-8 text-xs">
            <SelectValue placeholder="Bonded anchor" />
          </SelectTrigger>
          <SelectContent>
            {anchors.map((a) => (
              <SelectItem key={a.id} value={String(a.id)} className="text-xs">
                {a.name} (cap {a.provocation_cap})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {overCap && (
        <p className="text-[10px] text-destructive" data-testid="fury-over-cap-warning">
          Fury tier exceeds your bond with {selectedAnchor?.name}.
        </p>
      )}
    </div>
  );
}
