import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type EffortLevel = 'halfhearted' | 'normal' | 'all_out';

interface EffortSelectorProps {
  value: EffortLevel;
  onChange: (effort: EffortLevel) => void;
  disabled?: boolean;
}

const EFFORT_OPTIONS: { key: EffortLevel; label: string; tooltip: string }[] = [
  { key: 'halfhearted', label: 'Halfhearted', tooltip: 'Lower fatigue cost, -2 check penalty' },
  { key: 'normal', label: 'Normal', tooltip: 'Standard fatigue cost and check modifier' },
  { key: 'all_out', label: 'All Out', tooltip: 'Double fatigue cost, +2 check bonus' },
];

export function EffortSelector({ value, onChange, disabled }: EffortSelectorProps) {
  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label="Effort level">
      {EFFORT_OPTIONS.map((option) => {
        const isSelected = value === option.key;
        return (
          <Button
            key={option.key}
            type="button"
            size="sm"
            variant={isSelected ? 'default' : 'outline'}
            className={cn(
              'flex-1',
              isSelected && option.key === 'halfhearted' && 'bg-blue-600 hover:bg-blue-700',
              isSelected && option.key === 'all_out' && 'bg-orange-600 hover:bg-orange-700'
            )}
            disabled={disabled}
            title={option.tooltip}
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(option.key)}
          >
            {option.label}
          </Button>
        );
      })}
    </div>
  );
}
