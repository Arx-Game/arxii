/**
 * Species Card
 *
 * Displays a species for selection with stat bonuses.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Check, TrendingUp } from 'lucide-react';
import type { Species } from '../types';

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
  const bonuses = Object.entries(species.stat_bonuses)
    .filter(([, value]) => value !== 0)
    .map(([stat, value]) => ({
      stat: stat.charAt(0).toUpperCase() + stat.slice(1),
      value,
    }));

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
        {/* Stat Bonuses */}
        {bonuses.length > 0 && (
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-medium">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <span>Bonuses</span>
            </div>
            <div className="flex flex-wrap gap-1 pl-6">
              {bonuses.map(({ stat, value }) => (
                <Badge
                  key={stat}
                  variant="outline"
                  className={cn(
                    'text-xs',
                    value > 0 && 'border-green-500/50 bg-green-500/10 text-green-700',
                    value < 0 && 'border-red-500/50 bg-red-500/10 text-red-700'
                  )}
                >
                  {stat} {value > 0 ? '+' : ''}
                  {value}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Description */}
        <CardDescription className="line-clamp-3 text-sm">{species.description}</CardDescription>
      </CardContent>
    </Card>
  );
}
