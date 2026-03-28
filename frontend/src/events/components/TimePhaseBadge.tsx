import { Moon, Sun, Sunrise, Sunset } from 'lucide-react';
import type { TimePhase } from '../types';

const PHASE_CONFIG: Record<TimePhase, { label: string; icon: typeof Sun; className: string }> = {
  dawn: { label: 'Dawn', icon: Sunrise, className: 'text-amber-500' },
  day: { label: 'Day', icon: Sun, className: 'text-yellow-500' },
  dusk: { label: 'Dusk', icon: Sunset, className: 'text-orange-500' },
  night: { label: 'Night', icon: Moon, className: 'text-indigo-400' },
};

interface TimePhaseBadgeProps {
  phase: TimePhase;
  showLabel?: boolean;
}

export function TimePhaseBadge({ phase, showLabel = false }: TimePhaseBadgeProps) {
  const config = PHASE_CONFIG[phase];
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 ${config.className}`} title={config.label}>
      <Icon className="h-4 w-4" />
      {showLabel && <span className="text-xs">{config.label}</span>}
    </span>
  );
}
