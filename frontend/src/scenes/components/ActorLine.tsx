import { FormattedContent } from '@/components/FormattedContent';

interface ActorLineProps {
  /** The whole sentence the server rendered for this viewer (#3858); absent on older rows. */
  line?: string | null;
  /** The recorded text, the fallback when no line came. */
  content: string;
  /** The name on the card: the companion's for a companion pose, else the persona's. */
  actorName: string;
}

/**
 * The body of a pose or a say (#3858): the server's `line`, the actor in the
 * sentence, with the leading name set semibold so the eye finds the
 * actor. Presentation only: the name is the one the card already shows, and
 * the split happens only when the line opens with it (an emit, or a pose that
 * placed the name elsewhere, renders as sent). Without a line, the recorded
 * content renders as it always did.
 */
export function ActorLine({ line, content, actorName }: ActorLineProps) {
  if (!line) return <FormattedContent content={content} />;
  const opensWithActor = actorName.length > 0 && line.startsWith(actorName);
  if (!opensWithActor) {
    return (
      <span data-testid="actor-line">
        <FormattedContent content={line} />
      </span>
    );
  }
  return (
    <span data-testid="actor-line" data-actor={actorName}>
      <span className="font-semibold">{actorName}</span>
      <FormattedContent content={line.slice(actorName.length)} />
    </span>
  );
}
