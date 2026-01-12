/**
 * Stat Slider Component
 *
 * Individual stat input with +/- buttons for adjusting values.
 * Displays integer values (1-5) with validation.
 */

import { Button } from '@/components/ui/button';
import { Minus, Plus } from 'lucide-react';

interface StatSliderProps {
  name: string;
  value: number; // 1-5 scale
  onChange: (value: number) => void;
}

export function StatSlider({ name, value, onChange }: StatSliderProps) {
  const canDecrease = value > 1;
  const canIncrease = value < 5;

  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <span className="text-sm font-medium capitalize">{name}</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!canDecrease}
          onClick={() => onChange(value - 1)}
        >
          <Minus className="h-3 w-3" />
        </Button>
        <span className="w-16 text-center font-mono text-lg font-semibold">{value}</span>
        <Button
          variant="outline"
          size="sm"
          disabled={!canIncrease}
          onClick={() => onChange(value + 1)}
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
