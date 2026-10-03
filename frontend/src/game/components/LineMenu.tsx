import { useEffect } from 'react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export interface LineMenuProps {
  /** Where to open, in the frame's own coordinates; null is closed. */
  at: { x: number; y: number } | null;
  onClose: () => void;
  /** The menu's heading: who and when. */
  heading: string;
  folded: boolean;
  /** The character the line belongs to; absent on a note, so no per-character items. */
  personaName?: string;
  onFold: () => void;
  onHide: () => void;
  onFoldFrom?: () => void;
  onHideFrom?: () => void;
  onFoldAll: () => void;
  onExpandAll: () => void;
  onUnhideAll: () => void;
}

/**
 * The sorting menu on a feed line (#4128): information flow only, how text
 * renders. Opened by `useLineGestures` at the pointer, anchored to a zero-size
 * trigger placed there, so the same menu serves a right-click on the avatar
 * and a held press anywhere on the line.
 *
 * While it is open the browser's own context menu is suppressed at document
 * level: on Windows `contextmenu` fires on mouse up, after a held press has
 * already opened this one under the pointer, so the event lands on this menu
 * and a guard on the line never sees it.
 */
export function LineMenu({
  at,
  onClose,
  heading,
  folded,
  personaName,
  onFold,
  onHide,
  onFoldFrom,
  onHideFrom,
  onFoldAll,
  onExpandAll,
  onUnhideAll,
}: LineMenuProps) {
  const open = at !== null;
  useEffect(() => {
    if (!open) return;
    const swallow = (event: Event) => event.preventDefault();
    document.addEventListener('contextmenu', swallow);
    return () => document.removeEventListener('contextmenu', swallow);
  }, [open]);

  return (
    <DropdownMenu open={open} onOpenChange={(next) => !next && onClose()}>
      <DropdownMenuTrigger asChild>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute h-0 w-0"
          style={{ left: at?.x ?? 0, top: at?.y ?? 0 }}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        onCloseAutoFocus={(event) => event.preventDefault()}
        className="data-[state=closed]:!animate-none"
      >
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          {heading}
        </DropdownMenuLabel>
        <DropdownMenuItem onClick={onFold}>{folded ? 'Expand' : 'Minimize'}</DropdownMenuItem>
        <DropdownMenuItem onClick={onHide}>Hide</DropdownMenuItem>
        {personaName && onFoldFrom && onHideFrom && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onFoldFrom}>
              Minimize all from {personaName}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onHideFrom}>Hide all from {personaName}</DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onFoldAll}>Minimize all</DropdownMenuItem>
        <DropdownMenuItem onClick={onExpandAll}>Expand all</DropdownMenuItem>
        <DropdownMenuItem onClick={onUnhideAll}>Unhide all</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
