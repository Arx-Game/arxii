/**
 * ServerChangedBanner — surface when a record was updated server-side
 * while the user has unsaved edits.
 *
 * Adversarial review HIGH: prior to the useServerDraft fix, the dirty
 * draft would silently overwrite server-side changes on Save. This
 * banner is the user-visible side of that fix — clicking "Refresh"
 * discards the user's edits and pulls the latest server view.
 */

import { Button } from '@/components/ui/button';

interface Props {
  onPull: () => void;
  className?: string;
}

export function ServerChangedBanner({ onPull, className }: Props) {
  return (
    <div
      className={`flex items-center justify-between gap-2 rounded border border-amber-500/60 bg-amber-100/30 px-3 py-2 text-sm ${
        className ?? ''
      }`}
      data-testid="server-changed-banner"
      role="status"
    >
      <span>
        <strong>Updated server-side</strong> since you started editing. Refresh to discard your
        edits and pick up the latest, or keep editing and Save to overwrite.
      </span>
      <Button size="sm" variant="outline" onClick={onPull}>
        Refresh
      </Button>
    </div>
  );
}
