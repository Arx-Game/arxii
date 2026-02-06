/**
 * Stat Card Component
 *
 * Compact card for displaying a single stat with +/- controls.
 * Designed for use in a 3x3 grid layout.
 */

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Minus, Plus } from 'lucide-react';

interface StatCardProps {
  name: string;
  value: number;
  bonus?: number;
  onChange: (value: number) => void;
  onHover?: (name: string | null) => void;
  onTap?: () => void;
  canDecrease: boolean;
  canIncrease: boolean;
}

export function StatCard({
  name,
  value,
  bonus,
  onChange,
  onHover,
  onTap,
  canDecrease,
  canIncrease,
}: StatCardProps) {
  const effectiveBonus = bonus ?? 0;
  const total = value + effectiveBonus;
  const handleMouseEnter = () => {
    onHover?.(name);
  };

  const handleMouseLeave = () => {
    onHover?.(null);
  };

  const handleClick = () => {
    onTap?.();
  };

  const handleDecrease = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (canDecrease) {
      onChange(value - 1);
    }
  };

  const handleIncrease = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (canIncrease) {
      onChange(value + 1);
    }
  };

  return (
    <Card
      className="cursor-pointer p-3 transition-all hover:bg-accent/50 hover:ring-1 hover:ring-primary/50"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      <div className="flex flex-col items-center gap-2">
        <span className="text-sm font-medium capitalize">{name}</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={!canDecrease} onClick={handleDecrease}>
            <Minus className="h-3 w-3" />
          </Button>
          <span
            className="flex w-12 items-center justify-center gap-0.5 text-center font-mono text-xl font-semibold"
            title={
              effectiveBonus > 0
                ? `Base: ${value} | Bonus: +${effectiveBonus} | Total: ${total}`
                : undefined
            }
          >
            {total}
            {effectiveBonus > 0 && (
              <span className="text-xs font-normal text-emerald-500">+{effectiveBonus}</span>
            )}
          </span>
          <Button variant="outline" size="sm" disabled={!canIncrease} onClick={handleIncrease}>
            <Plus className="h-3 w-3" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
