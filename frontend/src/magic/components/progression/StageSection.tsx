import { Badge } from '@/components/ui/badge';
import { MilestoneCard } from './MilestoneCard';
import { MysteryMilestoneSlot } from './MysteryMilestoneSlot';
import type { ProgressionStage } from '@/magic/magicProgressionTypes';

interface StageSectionProps {
  stage: ProgressionStage;
}

/**
 * Renders a single progression stage with all its milestones.
 *
 * - Visually emphasizes the current stage with a "Current" badge and ring.
 * - Renders a MysteryMilestoneSlot when has_undiscovered is true.
 */
export function StageSection({ stage }: StageSectionProps) {
  return (
    <section
      aria-label={stage.stage_label}
      className={
        stage.is_current
          ? 'space-y-4 rounded-xl border-2 border-primary p-4'
          : 'space-y-4 rounded-xl border p-4'
      }
    >
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">{stage.stage_label}</h2>
        {stage.is_current && <Badge>Current</Badge>}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {stage.milestones.map((milestone, idx) => (
          <MilestoneCard key={`${milestone.kind}-${idx}`} milestone={milestone} />
        ))}
        {stage.has_undiscovered && <MysteryMilestoneSlot />}
      </div>
    </section>
  );
}
