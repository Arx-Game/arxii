import { useEffect, useRef, useState } from 'react';
import { Terminal } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { clearConsoleLines } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';
import { EvenniaMessage } from './EvenniaMessage';

interface StaffConsoleProps {
  character: MyRosterEntry['name'];
  /** True while the composer is in Commands mode: a new line opens the console by itself. */
  active: boolean;
}

/**
 * The staff console (#3857): a Console control in the composer's toolbar and
 * the sheet it opens over the play surface, holding every line the server
 * said back to a Commands-mode line. Monospace because the text is
 * telnet-shaped; the app's own sheet, title and controls around it, so it
 * never reads as a terminal bolted onto the page. Lines arriving while the
 * sheet is closed are counted on the control; Clear empties them.
 */
export function StaffConsole({ character, active }: StaffConsoleProps) {
  const dispatch = useAppDispatch();
  const lines = useAppSelector((state) => state.game.sessions[character]?.consoleLines ?? []);
  const [open, setOpen] = useState(false);
  const [seenCount, setSeenCount] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);
  // How many lines the auto-open has already answered, so closing the sheet
  // stays closed until the NEXT line arrives.
  const announcedRef = useRef(0);

  // A line arriving while a Commands-mode line is out opens the console; a
  // line arriving while the sheet is open is seen at once.
  useEffect(() => {
    if (lines.length > announcedRef.current) {
      announcedRef.current = lines.length;
      if (active && !open) setOpen(true);
    } else if (lines.length === 0) {
      announcedRef.current = 0;
    }
    if (open) setSeenCount(lines.filter((line) => !line.sent).length);
  }, [lines, active, open]);

  useEffect(() => {
    if (open) {
      setSeenCount(lines.filter((line) => !line.sent).length);
      endRef.current?.scrollIntoView({ block: 'end' });
    }
  }, [open, lines]);

  // Only the server's answers count as new; the staff member's own echoed
  // lines are theirs already.
  const answers = lines.filter((line) => !line.sent).length;
  const unseen = Math.max(0, answers - seenCount);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-h-8 items-center gap-1 rounded px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        aria-label={unseen > 0 ? `Console, ${unseen} new` : 'Console'}
      >
        <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
        Console
        {unseen > 0 && (
          <span className="rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">
            {unseen}
          </span>
        )}
      </button>
      {/* Beside the play surface, not over it (demo ruling): no dimming
          overlay, no focus trap, and a click into the composer keeps it open;
          Close, Clear and Escape are its controls. */}
      <Sheet open={open} onOpenChange={setOpen} modal={false}>
        <SheetContent
          side="right"
          hideOverlay
          hideClose
          onInteractOutside={(event) => event.preventDefault()}
          className="flex w-full flex-col gap-0 p-0 sm:max-w-xl"
        >
          <SheetHeader className="border-b px-4 py-3 text-left">
            <div className="flex items-center gap-3">
              <SheetTitle className="font-serif text-lg font-medium">Console</SheetTitle>
              <button
                type="button"
                onClick={() => dispatch(clearConsoleLines(character))}
                className="ml-auto rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                Close
              </button>
            </div>
            <SheetDescription className="text-xs">
              Staff commands and what the server said back.
            </SheetDescription>
          </SheetHeader>
          <div
            className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
            data-testid="staff-console-lines"
          >
            {lines.length === 0 ? (
              <p className="font-serif text-sm italic text-muted-foreground">
                Nothing yet. Pick Commands and type one.
              </p>
            ) : (
              lines.map((line) =>
                line.sent ? (
                  <p
                    key={line.id}
                    data-sent
                    className="whitespace-pre-wrap break-words font-mono text-[0.82rem] leading-relaxed text-muted-foreground"
                  >
                    {'\u203a '}
                    {line.content}
                  </p>
                ) : (
                  <EvenniaMessage
                    key={line.id}
                    content={line.content}
                    className="text-[0.82rem] leading-relaxed"
                  />
                )
              )
            )}
            <div ref={endRef} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
