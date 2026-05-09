import { Card, CardContent } from '@/components/ui/card';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import type { CharacterResonance, ResonanceBalance } from '../../types';

interface ResonanceBalanceCardProps {
  balance: ResonanceBalance;
  characterResonance: CharacterResonance | undefined;
}

/**
 * Small card showing a single ResonanceBalance entry.
 *
 * Displays: resonance name (from characterResonance if available, else resonance_id fallback),
 * spendable balance (large), lifetime_earned (small/subtle), and flavor_text on hover.
 */
export function ResonanceBalanceCard({ balance, characterResonance }: ResonanceBalanceCardProps) {
  const resonanceName = characterResonance?.resonance_name ?? `Resonance #${balance.resonance_id}`;
  const flavorText = balance.flavor_text;

  const cardBody = (
    <Card className="min-w-[120px] cursor-default text-center">
      <CardContent className="px-4 py-3">
        <div className="text-xs font-medium text-muted-foreground">{resonanceName}</div>
        <div
          className="mt-1 text-3xl font-bold tabular-nums"
          data-testid="resonance-balance-amount"
        >
          {balance.balance}
        </div>
        <div className="mt-1 text-xs text-muted-foreground" data-testid="resonance-lifetime-earned">
          {balance.lifetime_earned} lifetime
        </div>
      </CardContent>
    </Card>
  );

  if (!flavorText) {
    return cardBody;
  }

  return (
    <HoverCard>
      <HoverCardTrigger asChild>{cardBody}</HoverCardTrigger>
      <HoverCardContent className="w-56 text-sm" data-testid="resonance-flavor-text">
        {flavorText}
      </HoverCardContent>
    </HoverCard>
  );
}
