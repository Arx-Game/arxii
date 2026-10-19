import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { Interaction } from '@/scenes/types';

interface NpcResponseCardProps {
  /** The resolved action row aimed at the NPC; its content carries the outcome. */
  interaction: Interaction;
  /** The NPC's name, for the button. */
  npcName: string;
  onPoseAs: (interaction: Interaction) => void;
}

/** Shown when someone's action lands on the NPC you play; the button starts the reply. */
export function NpcResponseCard({ interaction, npcName, onPoseAs }: NpcResponseCardProps) {
  return (
    <Card data-testid="npc-response-card">
      <CardHeader className="pb-2">
        <CardTitle className="font-display text-base">{interaction.content}</CardTitle>
      </CardHeader>
      <CardContent>
        <Button size="sm" onClick={() => onPoseAs(interaction)}>
          Pose as {npcName}
        </Button>
      </CardContent>
    </Card>
  );
}
