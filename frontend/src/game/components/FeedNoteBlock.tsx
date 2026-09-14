import type { FeedNote } from '@/hooks/types';
import { EvenniaMessage } from './EvenniaMessage';
import { cn } from '@/lib/utils';

interface FeedNoteBlockProps {
  note: FeedNote;
}

/** The glyph a boxed note leads with; every other boxed kind gets ✦. */
const BOX_GLYPHS: Partial<Record<FeedNote['kind'], string>> = { look: '◎', error: '!' };

/**
 * One typed text line in the feed (#3856), styled by kind after the approved
 * demo (issue #3856, "One feed, filter chips"):
 *
 * - `look`: a boxed note with a ◎ glyph, the subject as a title when the server
 *   names one, and the appearance as prose in the reading face.
 * - `item` and `system`: the same box with a ✦ glyph, one muted sans line.
 * - `error`: the box in the destructive tokens with a ! glyph.
 * - `arrive` and `move`: a bare italic muted line, no box.
 * - `ambience`: the italic line with a hairline on the left.
 *
 * Every body goes through `EvenniaMessage` in prose presentation: a look
 * result, an item line and a gemit all reach the client as Evennia's HTML
 * (colour spans, `<br>`), and the terminal face would read as a transcript.
 */
export function FeedNoteBlock({ note }: FeedNoteBlockProps) {
  const { kind } = note;
  const time = new Date(note.timestamp).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });

  if (kind === 'arrive' || kind === 'move' || kind === 'ambience') {
    return (
      <div
        data-testid="feed-note"
        data-kind={kind}
        className={cn(
          'text-sm italic text-muted-foreground',
          kind === 'ambience' && 'max-w-[60ch] border-l-2 pl-2.5 opacity-85'
        )}
      >
        <EvenniaMessage content={note.content} presentation="prose" />
        <span className="sr-only">{time}</span>
      </div>
    );
  }

  const isError = kind === 'error';
  const isLook = kind === 'look';
  const glyph = BOX_GLYPHS[kind] ?? '✦';
  return (
    <div
      data-testid="feed-note"
      data-kind={kind}
      role={isError ? 'alert' : undefined}
      className={cn(
        'flex max-w-[64ch] items-start gap-2 rounded-sm border-l-2 bg-muted/50 px-2.5 py-1.5 font-sans text-xs text-muted-foreground',
        isError && 'border-destructive bg-destructive/10 text-destructive'
      )}
    >
      <span aria-hidden="true" className="w-3.5 flex-none text-center opacity-80">
        {glyph}
      </span>
      <div className="min-w-0 flex-1">
        {isLook && note.subject && <div className="font-medium">{note.subject}</div>}
        <EvenniaMessage
          content={note.content}
          presentation="prose"
          className={cn(isLook && 'font-serif text-[0.95rem] text-foreground')}
        />
      </div>
      <span className="sr-only">{time}</span>
    </div>
  );
}
