import type { FeedNote } from '@/hooks/types';
import { EvenniaMessage } from './EvenniaMessage';
import { cn } from '@/lib/utils';
import { FeedBlockFrame } from './FeedBlockFrame';
import { KIND_LABELS, feedItemKey } from '../feedChips';
import { VISION_FRAME_CLASS, VISION_GLYPH } from '@/worship/visionStyle';

interface FeedNoteBlockProps {
  note: FeedNote;
  /** Every loaded line's key, for the sorting menu's Minimize all / Expand all (#4128). */
  allKeys?: () => string[];
}

/** The glyph a boxed note leads with; every other boxed kind gets ✦. */
const BOX_GLYPHS: Partial<Record<FeedNote['kind'], string>> = { look: '◎', error: '!' };

/**
 * One typed text line in the feed (#3856), its kind told by glyph, frame,
 * italics and colour:
 *
 * - `look`: a boxed note with a ◎ glyph, the subject as a title when the server
 *   names one, and the appearance as prose.
 * - `item` and `system`: the same box with a ✦ glyph, one muted line.
 * - `error`: the box in the destructive tokens with a ! glyph.
 * - `arrive` and `move`: a bare italic muted line, no box.
 * - `ambience`: the italic line with a hairline on the left.
 * - `vision` (#3779): the emerald frame and glyph shared with the sheet's
 *   `VisionCard`.
 *
 * **No note sets its own size, face or width** (#4330): every one inherits the
 * reader's Display settings (`--play-prose-size`, `--play-prose-family`, the
 * column's line length) the way a pose does. #3856's demo drew them at 12px sans
 * in a 64-character box when the whole column was capped at 90ch; once Display
 * settings let the column fill the pane, that box became a narrow strip.
 *
 * Every body goes through `EvenniaMessage` in prose presentation: a look
 * result, an item line and a gemit all reach the client as Evennia's HTML
 * (colour spans, `<br>`), and the terminal face would read as a transcript.
 */
export function FeedNoteBlock({ note, allKeys }: FeedNoteBlockProps) {
  const time = new Date(note.timestamp).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });
  // Any block minimizes or dismisses, per viewer (#3856 PR 2); the stub names
  // the kind and the time, the way a pose's stub names its author.
  return (
    <FeedBlockFrame
      itemKey={feedItemKey('note', note.id)}
      stub={`${KIND_LABELS[note.kind]} · ${time}`}
      allKeys={allKeys}
    >
      <FeedNoteBody note={note} time={time} />
    </FeedBlockFrame>
  );
}

function FeedNoteBody({ note, time }: { note: FeedNote; time: string }) {
  const { kind } = note;

  if (kind === 'vision') {
    return (
      <div
        data-testid="feed-note"
        data-kind={kind}
        className={cn(VISION_FRAME_CLASS, 'flex items-start gap-2 px-3 py-2')}
      >
        <span
          aria-hidden="true"
          className="w-[1em] flex-none text-center text-emerald-600 dark:text-emerald-400"
        >
          {VISION_GLYPH}
        </span>
        <div className="min-w-0 flex-1">
          <EvenniaMessage
            content={note.content}
            presentation="prose"
            className="leading-relaxed text-foreground"
          />
        </div>
        <span className="sr-only">{time}</span>
      </div>
    );
  }

  if (kind === 'arrive' || kind === 'move' || kind === 'ambience') {
    return (
      <div
        data-testid="feed-note"
        data-kind={kind}
        className={cn(
          'italic text-muted-foreground',
          kind === 'ambience' && 'border-l-2 pl-2.5 opacity-85'
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
        'flex items-start gap-2 rounded-sm border-l-2 bg-muted/50 px-2.5 py-1.5 text-muted-foreground',
        // The dark palette's `destructive` is a deep red that vanishes on a
        // dark ground; the app's other error text pairs it with red-400.
        isError &&
          'border-destructive bg-destructive/10 text-destructive dark:border-red-400/70 dark:text-red-400'
      )}
    >
      <span aria-hidden="true" className="w-[1em] flex-none text-center opacity-80">
        {glyph}
      </span>
      <div className="min-w-0 flex-1">
        {/* Plain weight, as the demo draws it: only the description below is in full ink. */}
        {isLook && note.subject && <div>{note.subject}</div>}
        <EvenniaMessage
          content={note.content}
          presentation="prose"
          className={cn(isLook && 'text-foreground')}
        />
      </div>
      <span className="sr-only">{time}</span>
    </div>
  );
}
