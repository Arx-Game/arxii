import { useContext, useRef, useState, type ReactNode } from 'react';
import { FeedBlockControlsContext } from '../feedBlockControls';
import { useLineGestures } from '../hooks/useLineGestures';
import { LineMenu } from './LineMenu';

interface FeedBlockFrameProps {
  /** The block's `feedItemKey`. */
  itemKey: string;
  /** The one line a minimized block folds to: "Nyx · 11:29", "Look · 11:30". */
  stub: string;
  /** The character the block belongs to, for the per-character menu items (#4128). */
  persona?: { id: number; name: string };
  /** Every visible block key of one character, for "Minimize all from" and "Hide all from". */
  keysOf?: (personaId: number) => string[];
  /** Every visible block key, for "Minimize all". */
  allKeys?: () => string[];
  children: ReactNode;
}

const controlClass =
  'grid h-5 w-5 place-items-center rounded text-xs text-muted-foreground hover:bg-muted hover:text-foreground ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * Wraps any block in the column with the sorting gestures (#4128): a quick
 * right-click folds it to a one-line stub (and unfolds it again), a held
 * right-click, a long-press, or a right-click on the avatar opens `LineMenu`.
 * Nothing sits on the block itself. A folded block is its stub with a reopen
 * press and a hide control. Outside a provider (a reference view, a bare
 * test) the block renders as it is and no gesture does anything.
 */
export function FeedBlockFrame({
  itemKey,
  stub,
  persona,
  keysOf,
  allKeys,
  children,
}: FeedBlockFrameProps) {
  const controls = useContext(FeedBlockControlsContext);
  const rootRef = useRef<HTMLDivElement>(null);
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null);
  const folded = controls?.minimized.has(itemKey) ?? false;
  const gestures = useLineGestures({
    enabled: controls !== null,
    onFold: () => {
      if (!controls) return;
      if (folded) controls.restore(itemKey);
      else controls.minimize(itemKey);
    },
    onMenu: (clientX, clientY) => {
      const rect = rootRef.current?.getBoundingClientRect();
      setMenuAt({ x: clientX - (rect?.left ?? 0), y: clientY - (rect?.top ?? 0) });
    },
  });
  if (!controls) return <>{children}</>;

  const body = folded ? (
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
        aria-label="Hide"
        className={controlClass}
        onClick={() => controls.dismiss(itemKey)}
      >
        ×
      </button>
    </div>
  ) : (
    children
  );

  return (
    <div ref={rootRef} className="relative" data-feed-block={itemKey} {...gestures}>
      {body}
      <LineMenu
        at={menuAt}
        onClose={() => setMenuAt(null)}
        heading={stub}
        folded={folded}
        personaName={persona?.name}
        onFold={() => (folded ? controls.restore(itemKey) : controls.minimize(itemKey))}
        onHide={() => controls.dismiss(itemKey)}
        onFoldFrom={persona && keysOf ? () => controls.minimizeMany(keysOf(persona.id)) : undefined}
        onHideFrom={persona && keysOf ? () => controls.dismissMany(keysOf(persona.id)) : undefined}
        onFoldAll={() => controls.minimizeMany(allKeys ? allKeys() : [itemKey])}
        onExpandAll={() => controls.restoreAll()}
        onUnhideAll={() => controls.restoreDismissed()}
      />
    </div>
  );
}
