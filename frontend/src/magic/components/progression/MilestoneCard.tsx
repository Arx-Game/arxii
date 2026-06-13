import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ProgressionMilestone } from '@/magic/magicProgressionTypes';

interface MilestoneCardProps {
  milestone: ProgressionMilestone;
}

function EligibilityBadge({ eligibility }: { eligibility: ProgressionMilestone['eligibility'] }) {
  if (eligibility === 'already_have') {
    return <Badge variant="secondary">Attained</Badge>;
  }
  if (eligibility === 'eligible') {
    return <Badge>Available</Badge>;
  }
  if (eligibility === 'locked') {
    return <Badge variant="outline">Locked</Badge>;
  }
  return null;
}

/**
 * Card for a single ProgressionMilestone.
 *
 * Renders known milestones with eligibility badge, missing-requirements list,
 * XP cost, and a navigation CTA. Renders uncovered milestones with a muted
 * "heard of" treatment and a "Learn more" CTA when a route is available.
 */
export function MilestoneCard({ milestone }: MilestoneCardProps) {
  const navigate = useNavigate();
  const isKnown = milestone.tier === 'known';

  function handleCta() {
    if (milestone.route_name) {
      navigate(milestone.route_name);
    }
  }

  return (
    <Card data-testid="milestone-card">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className={isKnown ? '' : 'text-muted-foreground italic'}>
            {milestone.title}
          </CardTitle>
          {isKnown && <EligibilityBadge eligibility={milestone.eligibility} />}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {isKnown ? (
          <>
            <p className="text-sm text-muted-foreground">{milestone.summary}</p>

            {milestone.eligibility === 'locked' && milestone.missing.length > 0 && (
              <ul className="list-disc pl-4 text-xs text-muted-foreground space-y-0.5">
                {milestone.missing.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}

            {milestone.xp_cost != null && (
              <p className="text-xs font-medium">{milestone.xp_cost} XP</p>
            )}
          </>
        ) : (
          <p className="text-sm italic text-muted-foreground">
            Heard of — learn more to uncover what this holds.
          </p>
        )}

        {milestone.route_name && (
          <Button
            size="sm"
            variant={isKnown ? 'default' : 'outline'}
            onClick={handleCta}
            aria-label={isKnown ? `Open ${milestone.title}` : `Learn more about ${milestone.title}`}
          >
            {isKnown ? 'Open' : 'Learn more'}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
