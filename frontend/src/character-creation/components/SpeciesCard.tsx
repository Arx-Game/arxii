/**
 * Species Card
 *
 * Displays a species for selection with stat bonuses.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';
import type { Species } from '../types';
import { StatBonusBadges } from './StatBonusBadges';

interface SpeciesCardProps {
  species: Species;
  isSelected: boolean;
  onSelect: () => void;
  disabled?: boolean;
  onHover?: (species: Species | null) => void;
}

export function SpeciesCard({
  species,
  isSelected,
  onSelect,
  disabled,
  onHover,
}: SpeciesCardProps) {
  return (
    <Card
      className={cn(
        'relative cursor-pointer transition-all',
        isSelected && 'ring-2 ring-primary',
        !isSelected && !disabled && 'hover:ring-1 hover:ring-primary/50',
        disabled && 'cursor-not-allowed opacity-60'
      )}
      onClick={disabled ? undefined : onSelect}
      onMouseEnter={() => onHover?.(species)}
      onMouseLeave={() => onHover?.(null)}
    >
      {isSelected && (
        <div className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check className="h-4 w-4" />
        </div>
      )}

      <CardHeader className="pb-3">
        <CardTitle className="text-lg">{species.name}</CardTitle>
        {species.parent_name && (
          <span className="text-xs text-muted-foreground">{species.parent_name}</span>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <StatBonusBadges statBonuses={species.stat_bonuses} showHeader />
        <CardDescription className="line-clamp-3 text-sm">{species.description}</CardDescription>
      </CardContent>
    </Card>
  );
}
