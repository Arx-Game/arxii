/**
 * Stage 3: Lineage (Family) Selection
 *
 * Family selection filtered by area, orphan option, or "Unknown" for special heritage.
 * Includes tarot naming ritual for familyless characters (unknown origins and orphans).
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { HelpCircle, Shuffle, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useFamilies, useTarotCards, useUpdateDraft } from '../queries';
import type { CharacterDraft, Family, TarotCard } from '../types';
import { Stage } from '../types';

interface LineageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

export function LineageStage({ draft, onStageSelect }: LineageStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: families, isLoading: familiesLoading } = useFamilies(draft.selected_area?.id);

  // If no area selected, prompt user
  if (!draft.selected_area) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">Please select a starting area first.</p>
        <Button onClick={() => onStageSelect(Stage.ORIGIN)}>Go to Origin Selection</Button>
      </motion.div>
    );
  }

  // If beginnings has family_known = false, family is Unknown (e.g., Sleeper, Misbegotten)
  if (draft.selected_beginnings && !draft.selected_beginnings.family_known) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
        className="space-y-8"
      >
        <div>
          <h2 className="theme-heading text-2xl font-bold">Lineage</h2>
          <p className="mt-2 text-muted-foreground">Your character's family background.</p>
        </div>

        <Card className="max-w-md">
          <CardHeader>
            <div className="flex items-center gap-2">
              <HelpCircle className="h-5 w-5 text-amber-500" />
              <CardTitle className="text-base">Unknown Origins</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <CardDescription>
              As a {draft.selected_beginnings.name}, your true family origins are shrouded in
              mystery. This may be discovered through gameplay.
            </CardDescription>
          </CardContent>
        </Card>

        <TarotNamingRitual draft={draft} />
      </motion.div>
    );
  }

  // Prompt to select beginnings if not selected
  if (!draft.selected_beginnings) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">Please select a beginnings option first.</p>
        <Button onClick={() => onStageSelect(Stage.HERITAGE)}>Go to Heritage Selection</Button>
      </motion.div>
    );
  }

  // Normal upbringing - family selection
  const handleFamilySelect = (familyId: string) => {
    if (familyId === 'orphan') {
      updateDraft.mutate({ draftId: draft.id, data: { family_id: null, is_orphan: true } });
    } else {
      updateDraft.mutate({
        draftId: draft.id,
        data: { family_id: parseInt(familyId, 10), is_orphan: false },
      });
    }
  };

  const noblesFamilies = families?.filter((f) => f.family_type === 'noble') ?? [];
  const commonerFamilies = families?.filter((f) => f.family_type === 'commoner') ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">Lineage</h2>
        <p className="mt-2 text-muted-foreground">
          Choose your character's family. Your family name will be appended to your character's
          first name.
        </p>
      </div>

      {/* Orphan option */}
      <Card
        className={cn(
          'max-w-md cursor-pointer transition-all',
          draft.is_orphan && 'ring-2 ring-primary',
          !draft.is_orphan && 'hover:ring-1 hover:ring-primary/50'
        )}
        onClick={() => handleFamilySelect('orphan')}
      >
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Orphan / No Family</CardTitle>
            </div>
            <Switch checked={draft.is_orphan} />
          </div>
        </CardHeader>
        <CardContent>
          <CardDescription>
            Your character has no known family, or has been disowned.
          </CardDescription>
        </CardContent>
      </Card>

      {/* Tarot naming ritual for orphans */}
      {draft.is_orphan && <TarotNamingRitual draft={draft} />}

      {/* Family selection (disabled if orphan selected) */}
      {!draft.is_orphan && (
        <section className="space-y-4">
          <h3 className="theme-heading text-lg font-semibold">Select Family</h3>

          {familiesLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <div className="space-y-6">
              {/* Noble Houses */}
              {noblesFamilies.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-sm font-medium text-muted-foreground">Noble Houses</Label>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {noblesFamilies.map((family) => (
                      <FamilyCard
                        key={family.id}
                        family={family}
                        isSelected={draft.family?.id === family.id}
                        onSelect={() => handleFamilySelect(family.id.toString())}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Commoner Families */}
              {commonerFamilies.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-sm font-medium text-muted-foreground">
                    Commoner Families
                  </Label>
                  <Select
                    value={draft.family?.id?.toString() ?? ''}
                    onValueChange={handleFamilySelect}
                  >
                    <SelectTrigger className="w-full max-w-xs">
                      <SelectValue placeholder="Select a family" />
                    </SelectTrigger>
                    <SelectContent>
                      {commonerFamilies.map((family) => (
                        <SelectItem key={family.id} value={family.id.toString()}>
                          {family.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {families?.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No families available for this area. You may select orphan or contact staff.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </motion.div>
  );
}

// =============================================================================
// TarotNamingRitual Component
// =============================================================================

interface TarotNamingRitualProps {
  draft: CharacterDraft;
}

function TarotNamingRitual({ draft }: TarotNamingRitualProps) {
  const updateDraft = useUpdateDraft();
  const { data: cards, isLoading } = useTarotCards();

  const [selectedCardName, setSelectedCardName] = useState<string | null>(
    draft.draft_data.tarot_card_name ?? null
  );
  const [isReversed, setIsReversed] = useState<boolean>(draft.draft_data.tarot_reversed ?? false);

  // Sync local state when draft data changes externally
  useEffect(() => {
    setSelectedCardName(draft.draft_data.tarot_card_name ?? null);
    setIsReversed(draft.draft_data.tarot_reversed ?? false);
  }, [draft.draft_data.tarot_card_name, draft.draft_data.tarot_reversed]);

  const majorArcana = cards?.filter((c) => c.arcana_type === 'major') ?? [];
  const minorBySuit = {
    swords: cards?.filter((c) => c.suit === 'swords') ?? [],
    cups: cards?.filter((c) => c.suit === 'cups') ?? [],
    wands: cards?.filter((c) => c.suit === 'wands') ?? [],
    coins: cards?.filter((c) => c.suit === 'coins') ?? [],
  };

  const selectedCard = cards?.find((c) => c.name === selectedCardName) ?? null;

  const getSurname = (card: TarotCard, reversed: boolean): string => {
    return reversed ? card.surname_reversed : card.surname_upright;
  };

  const handleSelectCard = (cardName: string, reversed: boolean) => {
    setSelectedCardName(cardName);
    setIsReversed(reversed);
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          tarot_card_name: cardName,
          tarot_reversed: reversed,
        },
      },
    });
  };

  const handleToggleReversed = (reversed: boolean) => {
    if (selectedCardName === null) return;
    handleSelectCard(selectedCardName, reversed);
  };

  const handleRandomDraw = () => {
    if (!cards?.length) return;
    const card = cards[Math.floor(Math.random() * cards.length)];
    const reversed = Math.random() < 0.5;
    handleSelectCard(card.name, reversed);
  };

  const firstName = draft.draft_data.first_name;
  const currentSurname = selectedCard ? getSurname(selectedCard, isReversed) : null;

  if (isLoading) {
    return (
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Naming Ritual</h3>
        <div className="h-32 animate-pulse rounded bg-muted" />
      </section>
    );
  }

  return (
    <section className="space-y-6" data-testid="tarot-naming-ritual">
      {/* Section header */}
      <div>
        <h3 className="theme-heading text-lg font-semibold">Naming Ritual</h3>
        <p className="mt-1 text-sm italic text-muted-foreground">
          A Mirrormask draws from the Arcana to divine your name...
        </p>
      </div>

      {/* Surname preview */}
      <Card className="max-w-md">
        <CardContent className="pt-6">
          {currentSurname ? (
            <div className="text-center">
              {firstName ? (
                <p className="text-lg">
                  Your character will be known as{' '}
                  <span className="font-bold">
                    {firstName} {currentSurname}
                  </span>
                </p>
              ) : (
                <p className="text-lg">
                  Your surname: <span className="font-bold">{currentSurname}</span>
                </p>
              )}
              <p className="mt-1 text-sm text-muted-foreground">
                {selectedCard?.name} ({isReversed ? 'Reversed' : 'Upright'})
              </p>
            </div>
          ) : (
            <p className="text-center text-muted-foreground">
              Draw a card to determine your surname.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Controls: Random draw + orientation toggle */}
      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={handleRandomDraw} variant="outline">
          <Shuffle className="mr-2 h-4 w-4" />
          Draw Random Card
        </Button>

        {selectedCardName !== null && (
          <div className="flex items-center gap-2">
            <Label htmlFor="tarot-orientation" className="text-sm">
              Upright
            </Label>
            <Switch
              id="tarot-orientation"
              checked={isReversed}
              onCheckedChange={handleToggleReversed}
            />
            <Label htmlFor="tarot-orientation" className="text-sm">
              Reversed
            </Label>
          </div>
        )}
      </div>

      {/* Major Arcana */}
      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-muted-foreground">Major Arcana</h4>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {majorArcana.map((card) => (
            <TarotCardItem
              key={card.id}
              card={card}
              isSelected={selectedCardName === card.name}
              isReversed={selectedCardName === card.name ? isReversed : false}
              onSelect={() => handleSelectCard(card.name, isReversed)}
            />
          ))}
        </div>
      </div>

      {/* Minor Arcana */}
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-muted-foreground">Minor Arcana</h4>
        {(Object.entries(minorBySuit) as [string, TarotCard[]][]).map(([suit, suitCards]) => {
          if (suitCards.length === 0) return null;
          const suitSurname = suitCards[0]
            ? getSurname(suitCards[0], false)
            : suit.charAt(0).toUpperCase() + suit.slice(1);
          return (
            <div key={suit} className="space-y-2">
              <div className="flex items-center gap-2">
                <Label className="text-sm font-medium capitalize">{suit}</Label>
                <span className="text-xs text-muted-foreground">(Surname: {suitSurname})</span>
              </div>
              <div className="grid gap-1.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {suitCards.map((card) => (
                  <Card
                    key={card.id}
                    className={cn(
                      'cursor-pointer px-3 py-2 transition-all',
                      selectedCardName === card.name && 'ring-2 ring-primary',
                      selectedCardName !== card.name && 'hover:ring-1 hover:ring-primary/50'
                    )}
                    onClick={() => handleSelectCard(card.name, isReversed)}
                  >
                    <p className="text-sm font-medium">{card.name}</p>
                  </Card>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// =============================================================================
// TarotCardItem (Major Arcana card display)
// =============================================================================

interface TarotCardItemProps {
  card: TarotCard;
  isSelected: boolean;
  isReversed: boolean;
  onSelect: () => void;
}

function TarotCardItem({ card, isSelected, isReversed, onSelect }: TarotCardItemProps) {
  const surname = isSelected
    ? isReversed
      ? card.surname_reversed
      : card.surname_upright
    : card.surname_upright;

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all',
        isSelected && 'ring-2 ring-primary',
        !isSelected && 'hover:ring-1 hover:ring-primary/50'
      )}
      onClick={onSelect}
    >
      <CardHeader className="p-3">
        <CardTitle className="text-sm">{card.name}</CardTitle>
        <p className="text-xs font-medium text-primary/80">{surname}</p>
      </CardHeader>
      {card.description && (
        <CardContent className="px-3 pb-3 pt-0">
          <CardDescription className="line-clamp-2 text-xs">{card.description}</CardDescription>
        </CardContent>
      )}
    </Card>
  );
}

// =============================================================================
// FamilyCard Component
// =============================================================================

interface FamilyCardProps {
  family: Family;
  isSelected: boolean;
  onSelect: () => void;
}

function FamilyCard({ family, isSelected, onSelect }: FamilyCardProps) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all',
        isSelected && 'ring-2 ring-primary',
        !isSelected && 'hover:ring-1 hover:ring-primary/50'
      )}
      onClick={onSelect}
    >
      <CardHeader className="p-3">
        <CardTitle className="text-sm">{family.name}</CardTitle>
      </CardHeader>
      {family.description && (
        <CardContent className="px-3 pb-3 pt-0">
          <CardDescription className="text-xs">{family.description}</CardDescription>
        </CardContent>
      )}
    </Card>
  );
}
