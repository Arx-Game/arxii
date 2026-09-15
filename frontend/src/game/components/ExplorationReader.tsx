import { useMemo } from 'react';
import type { FeedNote, InteractionWsPayload } from '@/hooks/types';
import type { GameLifecycleState } from '@/store/gameSlice';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import { FeedNoteBlock } from './FeedNoteBlock';
import { FeedBlockFrame } from './FeedBlockFrame';
import { feedItemKey } from '../feedChips';
import { interleaveNotes } from '../feedRows';
import type { RoomData } from './RoomPanel';

interface ExplorationReaderProps {
  room: RoomData | null;
  ambientInteractions?: InteractionWsPayload[];
  lifecycleState?: GameLifecycleState;
  /** Typed text lines for this character (#3856), shown among the ambient poses by time. */
  notes?: FeedNote[];
  onRetry?: () => void;
}

/**
 * The quiet-room reader. Room facts stay structured and ambient interaction
 * frames are rendered as individual readable entries, never as a transcript.
 */
export function ExplorationReader({
  room,
  ambientInteractions = [],
  lifecycleState,
  notes = [],
  onRetry,
}: ExplorationReaderProps) {
  const awaitingSnapshot = lifecycleState === 'entering' && Boolean(room);
  const isStale =
    lifecycleState === 'reconnecting' || lifecycleState === 'entry-error' || awaitingSnapshot;
  const isAftermath = lifecycleState === 'aftermath';
  // One column (#3856): the room's structured poses and the character's own
  // notes (a look, an error, an arrival) in the order they happened, never a
  // section of notes below a section of poses.
  const rows = useMemo(
    () => interleaveNotes(ambientInteractions, notes),
    [ambientInteractions, notes]
  );
  return (
    <section
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
      style={{
        fontFamily: 'var(--play-prose-family, ui-sans-serif)',
        fontSize: 'var(--play-prose-size, 14px)',
      }}
      aria-label="Exploration"
      data-testid="exploration-reader"
    >
      <div className="mx-auto w-full max-w-[var(--play-reading-measure,90ch)] space-y-[var(--play-density-gap,1.25rem)] px-4 py-6 sm:px-6">
        <header className="border-b pb-4">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {isStale ? 'Last confirmed location' : 'You are here'}
          </p>
          <h1 className="mt-1 font-serif text-2xl">{room?.name ?? 'The world'}</h1>
          {isStale && (
            <p className="mt-2 text-sm text-muted-foreground" role="status">
              {awaitingSnapshot
                ? 'Refreshing your confirmed surroundings…'
                : 'This view may be out of date while the connection recovers.'}
            </p>
          )}
        </header>
        {isAftermath && (
          <div className="rounded-lg border bg-muted/30 p-4" role="status">
            <p className="font-medium">The scene has ended.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              You are back in exploration. The Here panel remains available for your next choice.
            </p>
          </div>
        )}
        {room && lifecycleState === 'entry-error' && (
          <div
            className="rounded-lg border border-destructive/40 bg-destructive/5 p-4"
            role="alert"
          >
            <p className="font-medium">The connection needs attention.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              This is the last confirmed location. Try again to refresh your surroundings.
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 min-h-11 rounded border px-4 text-sm font-medium hover:bg-accent"
              >
                Try again
              </button>
            )}
          </div>
        )}

        {!room ? (
          <div
            className="rounded-lg border border-dashed p-8 text-center"
            role={lifecycleState === 'entry-error' ? 'alert' : 'status'}
          >
            <h2 className="font-serif text-xl">
              {lifecycleState === 'entry-error'
                ? 'Entry could not be completed'
                : 'Finding your place'}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              <span className="sr-only">No messages yet. </span>
              {lifecycleState === 'entry-error'
                ? 'The world did not confirm this character. Check your connection and try again.'
                : 'Your confirmed surroundings will appear here when entry completes.'}
            </p>
            {lifecycleState === 'entry-error' && onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-4 min-h-11 rounded border px-4 text-sm font-medium hover:bg-accent"
              >
                Try again
              </button>
            )}
          </div>
        ) : (
          <>
            {room.description ? (
              <section aria-labelledby="exploration-description">
                <h2 id="exploration-description" className="sr-only">
                  Surroundings
                </h2>
                <p className="whitespace-pre-wrap text-[length:var(--play-prose-size,14px)] leading-relaxed">
                  {room.description}
                </p>
              </section>
            ) : (
              <section
                className="rounded-lg border border-dashed p-6"
                aria-labelledby="quiet-heading"
              >
                <h2 id="quiet-heading" className="font-serif text-xl">
                  The room is quiet.
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  <span className="sr-only">No messages yet. </span>
                  Look around the Here panel, inspect someone or something, or choose an exit.
                </p>
              </section>
            )}

            {rows.length > 0 && (
              <ol aria-label="Activity" className="space-y-3">
                {rows.map((row) =>
                  row.type === 'note' ? (
                    <li key={row.note.id} data-feed-row={`note:${row.note.id}`}>
                      <FeedNoteBlock note={row.note} />
                    </li>
                  ) : (
                    <li
                      key={`${row.item.id}:${row.item.timestamp}`}
                      data-feed-row={`interaction:${row.item.id}`}
                    >
                      <FeedBlockFrame
                        itemKey={feedItemKey('interaction', row.item.id)}
                        stub={`${row.item.persona.name} · ${new Date(row.item.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}
                      >
                        <article className="border-b pb-3 last:border-b-0">
                          <header className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <PersonaAvatar
                              source={{
                                name: row.item.persona.name,
                                thumbnailUrl: row.item.persona.thumbnail_url,
                              }}
                              size="sm"
                            />
                            <span className="font-medium text-foreground">
                              {row.item.persona.name}
                            </span>
                            <time dateTime={row.item.timestamp}>
                              {new Date(row.item.timestamp).toLocaleTimeString([], {
                                hour: 'numeric',
                                minute: '2-digit',
                              })}
                            </time>
                          </header>
                          <FormattedContent content={row.item.content} />
                        </article>
                      </FeedBlockFrame>
                    </li>
                  )
                )}
              </ol>
            )}
          </>
        )}
      </div>
    </section>
  );
}
