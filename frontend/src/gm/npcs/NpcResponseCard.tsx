import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { Interaction } from '@/scenes/types';

interface NpcResponseCardProps {
  /** The feed interaction another character aimed at the NPC being played. */
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
        <CardTitle className="font-display text-base">
          {interaction.persona.name} acted on {npcName}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="max-h-40 overflow-y-auto whitespace-pre-wrap text-sm italic text-muted-foreground">
          {interaction.content}
        </p>
        <Button size="sm" onClick={() => onPoseAs(interaction)}>
          Pose as {npcName}
        </Button>
      </CardContent>
    </Card>
  );
}
