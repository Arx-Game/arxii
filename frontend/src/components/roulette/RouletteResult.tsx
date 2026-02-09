import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { ConsequenceDisplay } from './types';
import { TIER_COLORS, DEFAULT_TIER_COLOR, ANIMATION_DURATION } from './constants';

interface RouletteResultProps {
  consequence: ConsequenceDisplay;
}

export function RouletteResult({ consequence }: RouletteResultProps) {
  const color = TIER_COLORS[consequence.tier_name] ?? DEFAULT_TIER_COLOR;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, height: 0 }}
      animate={{ opacity: 1, y: 0, height: 'auto' }}
      transition={{ duration: 0.4, delay: ANIMATION_DURATION.RESULT_DELAY }}
      className="overflow-hidden"
    >
      <div
        className={cn(
          'rounded-lg border p-6 text-center',
          color.bg,
          color.text,
          `shadow-lg ${color.glow}`
        )}
      >
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider opacity-70">
          {consequence.tier_name}
        </p>
        <p className="text-lg font-bold">{consequence.label}</p>
      </div>
    </motion.div>
  );
}
