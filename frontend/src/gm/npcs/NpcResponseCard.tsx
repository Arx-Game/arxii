import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { Interaction } from '@/scenes/types';

interface NpcResponseCardProps {
  /** The resolved action row aimed at the NPC; its content carries the outcome. */
  interaction: Interaction;
  /** The pose that attached the action, shown as the excerpt of what is being answered. */
  excerpt?: Interaction | null;
  /** The NPC's name, for the button. */
  npcName: string;
  onPoseAs: (interaction: Interaction) => void;
}

/** Shown when someone's action lands on the NPC you play; the button starts the reply. */
export function NpcResponseCard({ interaction, excerpt, npcName, onPoseAs }: NpcResponseCardProps) {
  const paragraphs = (excerpt?.content ?? '').split(/\n{2,}/).filter((p) => p.trim());
  return (
    <Card data-testid="npc-response-card">
      <CardHeader className="pb-2">
        <CardTitle className="font-display text-base">{interaction.content}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {paragraphs.length > 0 && (
          <div
            data-testid="npc-response-excerpt"
            className="max-h-48 space-y-2 overflow-y-auto rounded-md border bg-muted/40 p-2 text-sm italic text-muted-foreground"
          >
            {paragraphs.map((p, i) => (
              <p key={i} className="whitespace-pre-wrap">
                {p}
              </p>
            ))}
          </div>
        )}
        <Button size="sm" onClick={() => onPoseAs(interaction)}>
          Pose as {npcName}
        </Button>
      </CardContent>
    </Card>
  );
}
