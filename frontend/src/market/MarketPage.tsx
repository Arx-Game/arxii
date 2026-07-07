/**
 * Market center (#2066): browse capital squares, buy stock and unfinished
 * wares, finish purchases with your own prose, and find crafters' shops.
 *
 * Two-tier geography (design tenet): goods buy remotely or in person; the
 * shop directory only *advertises* services — using one means visiting the
 * crafter's shop on the grid.
 */

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import {
  dispatchMarketAction,
  getMarketSquares,
  getServiceOffers,
  type MarketSquare,
  type WareListing,
} from './api';

export function MarketPage() {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myEntries.find((entry) => entry.name === activeCharacter) ?? null,
    [myEntries, activeCharacter]
  );
  const characterId = activeEntry?.character_id ?? undefined;

  const { data: squares = [], isLoading } = useQuery({
    queryKey: ['market-squares'],
    queryFn: getMarketSquares,
  });
  const { data: offers = [] } = useQuery({
    queryKey: ['market-service-offers'],
    queryFn: getServiceOffers,
  });

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6">
      <div>
        <h1 className="theme-heading text-3xl font-bold">The Markets</h1>
        <p className="mt-2 text-muted-foreground">
          Materials and ready wares trade in the squares. Unfinished pieces are yours to name and
          describe. For custom work, visit a crafter&apos;s shop.
        </p>
      </div>

      {isLoading && <div className="h-24 animate-pulse rounded bg-muted" />}
      {squares.map((square) => (
        <SquareSection key={square.id} square={square} characterId={characterId} />
      ))}

      <Card>
        <CardHeader>
          <CardTitle>Crafters&apos; Shops</CardTitle>
        </CardHeader>
        <CardContent>
          {offers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No standing service offers yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {offers.map((offer) => (
                <li key={offer.id} className="flex items-baseline justify-between">
                  <span>
                    <span className="font-medium">{offer.crafter_name}</span> —{' '}
                    {offer.recipe_kind.replace('_', ' ')}
                  </span>
                  <span className="text-muted-foreground">
                    {offer.fee}c · visit their shop to commission
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface SquareSectionProps {
  square: MarketSquare;
  characterId: number | undefined;
}

function SquareSection({ square, characterId }: SquareSectionProps) {
  const queryClient = useQueryClient();
  const buy = useMutation({
    mutationFn: ({
      key,
      kwargs,
    }: {
      key: 'market_buy_stock' | 'market_buy_ware';
      kwargs: Record<string, unknown>;
    }) => dispatchMarketAction(characterId!, key, kwargs),
    onSuccess: (message) => {
      toast.success(message);
      void queryClient.invalidateQueries({ queryKey: ['market-squares'] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{square.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {square.stalls.map((stall) => (
          <div key={stall.id}>
            <h3 className="mb-2 font-semibold">
              {stall.name}
              {stall.owner_name && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {stall.owner_name}&apos;s stall
                </span>
              )}
            </h3>
            <ul className="space-y-2 text-sm">
              {stall.stock_listings.map((stock) => (
                <li key={`s${stock.id}`} className="flex items-center justify-between">
                  <span>{stock.template_name}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-muted-foreground">{stock.price}c</span>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!characterId || buy.isPending}
                      onClick={() =>
                        buy.mutate({ key: 'market_buy_stock', kwargs: { listing_id: stock.id } })
                      }
                    >
                      Buy
                    </Button>
                  </span>
                </li>
              ))}
              {stall.ware_listings.map((ware) => (
                <WareRow
                  key={`w${ware.id}`}
                  ware={ware}
                  disabled={!characterId || buy.isPending}
                  onBuy={() =>
                    buy.mutate({ key: 'market_buy_ware', kwargs: { listing_id: ware.id } })
                  }
                />
              ))}
              {stall.stock_listings.length === 0 && stall.ware_listings.length === 0 && (
                <li className="text-muted-foreground">Nothing on the shelves.</li>
              )}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

interface WareRowProps {
  ware: WareListing;
  disabled: boolean;
  onBuy: () => void;
}

function WareRow({ ware, disabled, onBuy }: WareRowProps) {
  return (
    <li className="flex items-center justify-between">
      <span>
        {ware.item_name}
        <Badge variant="outline" className="ml-2">
          unfinished — you describe it
        </Badge>
        <span className="ml-2 text-xs text-muted-foreground">by {ware.seller_name}</span>
      </span>
      <span className="flex items-center gap-2">
        <span className="text-muted-foreground">{ware.price}c</span>
        <Button size="sm" variant="outline" disabled={disabled} onClick={onBuy}>
          Buy
        </Button>
      </span>
    </li>
  );
}

/**
 * FinishWareForm — name and describe a purchased ware (the prose is yours).
 * Rendered from the toast follow-up / inventory flows; exported for reuse.
 */
export function FinishWareForm({
  characterId,
  finishingPassId,
}: {
  characterId: number;
  finishingPassId: number;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const finish = useMutation({
    mutationFn: () =>
      dispatchMarketAction(characterId, 'market_finish_ware', {
        finishing_pass_id: finishingPassId,
        item_name: name,
        description,
      }),
    onSuccess: (message) => toast.success(message),
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className="space-y-2">
      <Input
        placeholder="Name the piece"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <Textarea
        placeholder="Describe it in your own words — this prose is yours."
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <Button
        size="sm"
        disabled={finish.isPending || (!name && !description)}
        onClick={() => finish.mutate()}
      >
        Finish
      </Button>
    </div>
  );
}
