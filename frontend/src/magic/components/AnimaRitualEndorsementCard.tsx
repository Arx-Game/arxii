/**
 * AnimaRitualEndorsementCard (#5280, Screen 2 of the approved demo): the partner's card for an
 * anima ritual that reached for them. It sits beside the scene's `ConsentPrompt` and shows one
 * block per ritual waiting for the answer, with Endorse, Withhold and the line about what the
 * ritual does to the partner's fatigue. An NPC partner has no card: the server lists nothing.
 */
import { Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { extractErrorMessage } from '@/lib/errors';
import { useAnimaRitualEndorsements, useAnswerAnimaRitual } from '@/rituals/queries';

interface AnimaRitualEndorsementCardProps {
  sceneId: string;
}

export function AnimaRitualEndorsementCard({ sceneId }: AnimaRitualEndorsementCardProps) {
  const { data } = useAnimaRitualEndorsements(Number(sceneId));
  const answer = useAnswerAnimaRitual();

  const waiting = data?.results ?? [];
  if (waiting.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="anima-ritual-endorsements">
      {waiting.map((row) => (
        <div
          key={row.id}
          className="flex flex-wrap items-center gap-3 rounded-md border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30"
          data-testid="anima-ritual-endorsement"
        >
          <div className="min-w-0 flex-1 basis-56">
            <p className="text-sm font-medium">{row.prompt}</p>
            {row.partner_line && (
              <p className="mt-1 text-xs text-muted-foreground">{row.partner_line}</p>
            )}
            {answer.isError && answer.variables?.id === row.id && (
              <p role="alert" className="mt-1 text-xs text-destructive">
                {extractErrorMessage(answer.error, 'Failed to answer the ritual')}
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              size="sm"
              onClick={() => answer.mutate({ id: row.id, endorse: true })}
              disabled={answer.isPending}
            >
              <Check className="mr-1 h-3.5 w-3.5" />
              Endorse
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => answer.mutate({ id: row.id, endorse: false })}
              disabled={answer.isPending}
            >
              <X className="mr-1 h-3.5 w-3.5" />
              Withhold
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
