import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { useAnswerNpcLoan, type NpcOffer } from './queries';

interface NpcOfferCardProps {
  loan: NpcOffer;
  /** The Guide's acting character, who the answer is dispatched as. */
  characterId: number;
}

/** An NPC lent to this Guide: the GM's notes, then Accept or Decline. */
export function NpcOfferCard({ loan, characterId }: NpcOfferCardProps) {
  const answer = useAnswerNpcLoan(characterId);
  const respond = (accept: boolean) => answer.mutate({ loanId: loan.loan_id, accept });
  const paragraphs = loan.notes_for_player.split(/\n{2,}/).filter((p) => p.trim());

  return (
    <Card data-testid="npc-offer-card">
      <CardHeader className="pb-2">
        <CardTitle className="font-display text-base">
          {loan.name}, offered by {loan.offered_by_name}
        </CardTitle>
        {loan.scene_title && <p className="text-xs text-muted-foreground">{loan.scene_title}</p>}
      </CardHeader>
      <CardContent className="space-y-3">
        {paragraphs.length > 0 && (
          <div className="max-h-64 space-y-2 overflow-y-auto text-sm">
            {paragraphs.map((p, i) => (
              <p key={i} className="whitespace-pre-wrap">
                {p}
              </p>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <Button size="sm" disabled={answer.isPending} onClick={() => respond(true)}>
            Accept
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={answer.isPending}
            onClick={() => respond(false)}
          >
            Decline
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
