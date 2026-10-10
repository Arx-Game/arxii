import { FormattedContent } from '@/components/FormattedContent';
import { markMatches, useFeedFind } from '@/game/feedFind';

interface ActorLineProps {
  /** The whole sentence the server rendered for this viewer (#3858); absent on older rows. */
  line?: string | null;
  /** The recorded text, the fallback when no line came. */
  content: string;
  /** The name on the card: the companion's for a companion pose, else the persona's. */
  actorName: string;
}

/**
 * A lead-in the server puts before the actor (#4128): the whisper emote's
 * "Quietly, " and tabletalk's "At <place>, ", alone or together. The server's
 * grammar is the one source; this only finds where the name starts.
 */
const LEAD_IN = /^(?:At [^,]+, )?(?:Quietly, )?/;

/**
 * The body of a pose or a say (#3858): the server's `line`, the actor in the
 * sentence, with the name set semibold so the eye finds the actor, after any
 * lead-in (#4128). Presentation only: the name is the one the line already
 * carries, and the split happens only when the line opens with it, or with a
 * lead-in and then it (an emit, or a pose that placed the name elsewhere,
 * renders as sent). Without a line, the recorded content renders as it always
 * did.
 */
export function ActorLine({ line, content, actorName }: ActorLineProps) {
  const find = useFeedFind();
  if (!line) return <FormattedContent content={content} />;
  const leadIn = LEAD_IN.exec(line)?.[0] ?? '';
  const opensWithActor = actorName.length > 0 && line.startsWith(actorName, leadIn.length);
  if (!opensWithActor) {
    return (
      <span data-testid="actor-line">
        <FormattedContent content={line} />
      </span>
    );
  }
  return (
    <span data-testid="actor-line" data-actor={actorName}>
      {markMatches(leadIn, find)}
      <span className="font-semibold">{markMatches(actorName, find)}</span>
      <FormattedContent content={line.slice(leadIn.length + actorName.length)} />
    </span>
  );
}
