/**
 * PathIntentCard — shows the character's current declared path intent and
 * offers a button to clear it. Used on the character sheet page when an
 * obvious composition point is available.
 */

import { usePathIntent, useClearPathIntent } from '@/magic/queries';
import { Button } from '@/components/ui/button';

export function PathIntentCard() {
  const { data, isLoading } = usePathIntent();
  const clear = useClearPathIntent();

  if (isLoading) return null;
  if (!data?.intent) return null;

  const { intent } = data;

  return (
    <div
      data-testid="path-intent-card"
      className="rounded-md border border-amber-500/40 bg-amber-950/20 p-3 text-sm"
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-semibold text-amber-300">Declared Path Intent</span>
        <Button
          variant="outline"
          size="sm"
          className="h-6 px-2 py-0 text-xs"
          disabled={clear.isPending}
          onClick={() => clear.mutate()}
          data-testid="path-intent-clear"
        >
          Clear
        </Button>
      </div>
      <div className="font-medium text-foreground">{intent.intended_path.name}</div>
      <div className="text-muted-foreground">{intent.intended_path.stage_display}</div>
    </div>
  );
}
