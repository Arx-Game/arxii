import type { InteractionWsPayload } from '@/hooks/types';
import type { GameLifecycleState } from '@/store/gameSlice';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import type { RoomData } from './RoomPanel';

interface ExplorationReaderProps {
  room: RoomData | null;
  ambientInteractions?: InteractionWsPayload[];
  lifecycleState?: GameLifecycleState;
  diagnostics?: string[];
  ambientNotices?: string[];
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
  diagnostics = [],
  ambientNotices = [],
  onRetry,
}: ExplorationReaderProps) {
  const awaitingSnapshot = lifecycleState === 'entering' && Boolean(room);
  const isStale =
    lifecycleState === 'reconnecting' || lifecycleState === 'entry-error' || awaitingSnapshot;
  const isAftermath = lifecycleState === 'aftermath';
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
        {diagnostics.length > 0 && (
          <aside
            className="rounded-lg border border-destructive/40 bg-destructive/5 p-4"
            aria-label="Connection notices"
          >
            <p className="font-medium">Connection notice</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-muted-foreground">
              {diagnostics.map((message, index) => (
                <li key={`${message}:${index}`}>{message}</li>
              ))}
            </ul>
          </aside>
        )}
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

            {ambientNotices.length > 0 && (
              <section aria-labelledby="ambient-notices-heading" className="space-y-2">
                <h2
                  id="ambient-notices-heading"
                  className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  Nearby activity
                </h2>
                {ambientNotices.map((notice, index) => (
                  <p
                    key={`${notice}:${index}`}
                    className="rounded border-l-2 border-primary/40 pl-3 text-sm"
                  >
                    {notice}
                  </p>
                ))}
              </section>
            )}
            {ambientInteractions.length > 0 && (
              <section aria-labelledby="ambient-heading" className="space-y-3">
                <h2
                  id="ambient-heading"
                  className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  Nearby
                </h2>
                {ambientInteractions.map((interaction) => (
                  <article
                    key={`${interaction.id}:${interaction.timestamp}`}
                    className="border-b pb-3 last:border-b-0"
                  >
                    <header className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <PersonaAvatar
                        source={{
                          name: interaction.persona.name,
                          thumbnailUrl: interaction.persona.thumbnail_url,
                        }}
                        size="sm"
                      />
                      <span className="font-medium text-foreground">
                        {interaction.persona.name}
                      </span>
                      <time dateTime={interaction.timestamp}>
                        {new Date(interaction.timestamp).toLocaleTimeString([], {
                          hour: 'numeric',
                          minute: '2-digit',
                        })}
                      </time>
                    </header>
                    <FormattedContent content={interaction.content} />
                  </article>
                ))}
              </section>
            )}
          </>
        )}
      </div>
    </section>
  );
}
