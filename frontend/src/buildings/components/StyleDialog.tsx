import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import { useArchitecturalStylesQuery } from '../queries';
import type { RoomBuilderActionKey } from '../types';

interface StyleDialogProps {
  /** The entry room of the building (dispatch anchor). */
  anchorRoomId: number;
  /** The active puppet's ObjectDB pk (viewer context for the per-viewer read). */
  characterId: number;
  /** The building's current style name, or null if unset. */
  currentStyle: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/**
 * Pick an architectural style to dress the building in. Mirrors RenovationDialog
 * (catalog picker → runAction). The endpoint already filters to styles the
 * viewer can build (default styles always; throwback styles only when codex-known).
 */
export function StyleDialog({
  anchorRoomId,
  characterId,
  currentStyle,
  open,
  onOpenChange,
  runAction,
}: StyleDialogProps) {
  const styles = useArchitecturalStylesQuery(characterId, '', open);

  const apply = (styleName: string) => {
    runAction('set_building_style', { room_id: anchorRoomId, style: styleName });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Set building style</DialogTitle>
        </DialogHeader>
        <div className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          {styles.isLoading && <p className="text-sm text-muted-foreground">Loading styles…</p>}
          {(styles.data?.results ?? []).map((style) => (
            <div key={style.id} className="rounded-md border p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold">
                  {style.name}
                  {style.name === currentStyle && (
                    <span className="ml-2 text-xs text-muted-foreground">(current)</span>
                  )}
                </span>
                <Button
                  size="sm"
                  variant={style.name === currentStyle ? 'secondary' : 'default'}
                  onClick={() => apply(style.name)}
                  disabled={style.name === currentStyle}
                >
                  Apply
                </Button>
              </div>
              {style.description && (
                <p className="mt-1 text-xs text-muted-foreground">{style.description}</p>
              )}
              <div className="mt-1 flex flex-wrap gap-1">
                {style.is_default ? (
                  <Badge variant="outline">Common</Badge>
                ) : (
                  <Badge variant="secondary">Throwback</Badge>
                )}
                {style.prestige_bonus ? (
                  <Badge variant="outline">+{style.prestige_bonus} prestige</Badge>
                ) : null}
                {style.cost_multiplier && style.cost_multiplier !== '1' && (
                  <Badge variant="outline">×{style.cost_multiplier} cost</Badge>
                )}
              </div>
            </div>
          ))}
          {styles.data && styles.data.results.length === 0 && (
            <p className="text-sm text-muted-foreground">No styles available.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
