/**
 * Species Option Card
 *
 * Displays a species-area combination with cost, bonuses, and accessibility.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Check, Coins, Lock, TrendingUp } from 'lucide-react';
import type { SpeciesOption } from '../types';

interface SpeciesOptionCardProps {
  option: SpeciesOption;
  isSelected: boolean;
  onSelect: () => void;
  disabled?: boolean;
}

export function SpeciesOptionCard({
  option,
  isSelected,
  onSelect,
  disabled,
}: SpeciesOptionCardProps) {
  const isLocked = !option.is_accessible;
  const isDisabled = disabled || isLocked;

  const bonuses = Object.entries(option.stat_bonuses)
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
        !isSelected && !isDisabled && 'hover:ring-1 hover:ring-primary/50',
        isDisabled && 'cursor-not-allowed opacity-60'
      )}
      onClick={isDisabled ? undefined : onSelect}
    >
      {isSelected && (
        <div className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check className="h-4 w-4" />
        </div>
      )}

      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-lg">{option.species.name}</CardTitle>
          {isLocked && (
            <Badge variant="secondary" className="shrink-0">
              <Lock className="mr-1 h-3 w-3" />
              Trust {option.trust_required}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Cost */}
        <div className="flex items-center gap-2 text-sm">
          <Coins className="h-4 w-4 text-amber-500" />
          <span className="font-medium">
            {option.cg_point_cost === 0 ? 'Free' : `${option.cg_point_cost} points`}
          </span>
        </div>

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
        <CardDescription className="text-sm">
          {option.description_override || option.species.description}
        </CardDescription>
      </CardContent>
    </Card>
  );
}
