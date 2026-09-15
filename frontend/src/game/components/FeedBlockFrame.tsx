import { useContext, type ReactNode } from 'react';
import { FeedBlockControlsContext } from '../feedBlockControls';

interface FeedBlockFrameProps {
  /** The block's `feedItemKey`. */
  itemKey: string;
  /** The one line a minimised block folds to: "Nyx · 11:29", "Look · 11:30". */
  stub: string;
  children: ReactNode;
}

const controlClass =
  'grid h-5 w-5 place-items-center rounded text-xs text-muted-foreground hover:bg-muted hover:text-foreground ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * Wraps any block in the column with the demo's hover controls: minimise and
 * dismiss at the top right, shown on hover or keyboard focus. A minimised
 * block is its stub with a reopen press and the dismiss control. Outside a
 * provider (a reference view, a bare test) the block renders as it is.
 */
export function FeedBlockFrame({ itemKey, stub, children }: FeedBlockFrameProps) {
  const controls = useContext(FeedBlockControlsContext);
  if (!controls) return <>{children}</>;

  if (controls.minimized.has(itemKey)) {
    return (
      <div
        data-feed-stub={itemKey}
        className="flex items-center gap-2 py-0.5 text-xs text-muted-foreground"
      >
        <button
          type="button"
          className="underline decoration-dotted underline-offset-2 hover:text-foreground"
          onClick={() => controls.restore(itemKey)}
        >
          {stub}
        </button>
        <span aria-hidden="true" className="h-px flex-1 bg-border" />
        <button
          type="button"
          aria-label="Dismiss"
          className={controlClass}
          onClick={() => controls.dismiss(itemKey)}
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div className="group relative" data-feed-block={itemKey}>
      {children}
      <div className="absolute right-0 top-0 flex gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          aria-label="Minimise"
          className={controlClass}
          onClick={() => controls.minimize(itemKey)}
        >
          –
        </button>
        <button
          type="button"
          aria-label="Dismiss"
          className={controlClass}
          onClick={() => controls.dismiss(itemKey)}
        >
          ×
        </button>
      </div>
    </div>
  );
}
