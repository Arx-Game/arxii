/**
 * PreviewDialog (#3477 Task 6) — the manuscript's Preview button: shows the
 * room's real payload two ways, since the same room reads differently on
 * the web card and over telnet. Both renderings use the CURRENT (possibly
 * unsaved) name/description the viewer is typing — matching the prototype's
 * own `$("msText").value` read — never the last-saved server copy, since the
 * whole point of Preview is checking prose before you commit to Save.
 *
 * No fabricated content: the prototype's telnet mock hardcodes a GM presence
 * line ("Apostate (GM) is here.") that has no real backing data here, so
 * it's left out rather than invented — exits and the breadcrumb-derived
 * location line are the only "occupancy"-adjacent facts this dialog has.
 */
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Plate } from '@/components/folio';

export interface PreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  description: string;
  /** Outermost-first ancestor names, e.g. ["Arx", "Central Ward"] — the room itself excluded. */
  locationPath: string[];
  exitNames: string[];
  artUrl: string | null;
}

export function PreviewDialog({
  open,
  onOpenChange,
  name,
  description,
  locationPath,
  exitNames,
  artUrl,
}: PreviewDialogProps) {
  const exitsLine = exitNames.length > 0 ? exitNames.join(', ') : 'none';
  const locationLine = locationPath.length > 0 ? locationPath.join(', ') : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle className="sr-only">Preview: {name || 'unnamed room'}</DialogTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <Plate className="p-4" data-testid="preview-web-card">
            {artUrl && (
              <img
                src={artUrl}
                alt=""
                className="mb-2 aspect-video w-full object-cover"
                data-testid="preview-art"
              />
            )}
            <h3 className="theme-heading text-lg [font-variant:small-caps]">
              {name || 'unnamed room'}
            </h3>
            {locationLine && (
              <p className="font-body text-xs italic text-muted-foreground">{locationLine}</p>
            )}
            <p className="mt-2 font-body text-sm">{description || '(no description yet)'}</p>
            <p className="mt-3 text-xs text-muted-foreground">
              <span className="font-medium">Exits:</span> {exitsLine}
            </p>
          </Plate>

          <div
            className="whitespace-pre-wrap bg-black p-4 font-mono text-sm text-green-400"
            data-testid="preview-telnet"
          >
            <div>{name || 'unnamed room'}</div>
            {locationLine && <div className="text-green-600">{locationLine}</div>}
            <div className="mt-2">{description || '(no description yet)'}</div>
            <div className="mt-2">Exits: {exitsLine}.</div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
