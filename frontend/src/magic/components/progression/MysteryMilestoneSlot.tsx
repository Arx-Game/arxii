import { Card, CardContent } from '@/components/ui/card';

/**
 * Content-free placeholder card for an undiscovered milestone.
 *
 * Renders a muted, generic teaser — no count, no names, no specifics.
 */
export function MysteryMilestoneSlot() {
  return (
    <Card data-testid="mystery-slot" className="border-dashed opacity-60">
      <CardContent className="flex items-center justify-center py-8">
        <p className="text-sm italic text-muted-foreground">
          Something stirs here, yet unknown to you.
        </p>
      </CardContent>
    </Card>
  );
}
