import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type EffortLevel = 'very_low' | 'low' | 'medium' | 'high' | 'extreme';

interface EffortSelectorProps {
  value: EffortLevel;
  onChange: (effort: EffortLevel) => void;
  disabled?: boolean;
}

const EFFORT_OPTIONS: {
  key: EffortLevel;
  label: string;
  tooltip: string;
  selectedClass: string;
}[] = [
  {
    key: 'very_low',
    label: 'Very Low',
    tooltip: 'Minimal fatigue cost (min 1), -3 check penalty',
    selectedClass: 'bg-rose-200 hover:bg-rose-300 text-rose-900',
  },
  {
    key: 'low',
    label: 'Low',
    tooltip: 'Half fatigue cost, -1 check penalty',
    selectedClass: 'bg-rose-300 hover:bg-rose-400 text-rose-950',
  },
  {
    key: 'medium',
    label: 'Medium',
    tooltip: 'Standard fatigue cost, no check modifier',
    selectedClass: '',
  },
  {
    key: 'high',
    label: 'High',
    tooltip: 'Double fatigue cost, +2 check bonus. Collapse risk when overexerted',
    selectedClass: 'bg-red-600 hover:bg-red-700',
  },
  {
    key: 'extreme',
    label: 'Extreme',
    tooltip: '3.5x fatigue cost, +4 check bonus. Collapse risk when overexerted',
    selectedClass: 'bg-red-900 hover:bg-red-950',
  },
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
            className={cn('flex-1', isSelected && option.selectedClass)}
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
