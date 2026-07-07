/**
 * Stage 3: Lineage (Family) Selection
 *
 * Family selection filtered by area, orphan option, or "Unknown" for special heritage.
 * Includes tarot naming ritual for familyless characters (unknown origins and orphans).
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
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
import { CodexTerm } from '@/codex/components/CodexTerm';
import {
  useCGExplanations,
  useClaimableTitles,
  useFamilies,
  useHouseClaim,
  useNamingRitualConfig,
  useTarotCards,
  useUpdateDraft,
  useFamilySlots,
} from '../queries';
import { submitHouseClaim, type ClaimableTitle, type HouseClaimPayload } from '../api';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import type { CharacterDraft, Family, KinSlot, KinSlotPool, TarotCard } from '../types';
import { Stage } from '../types';

interface LineageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

export function LineageStage({ draft, onStageSelect }: LineageStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
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
          <h2 className="theme-heading text-2xl font-bold">{copy?.lineage_heading ?? ''}</h2>
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
  const isOrphan = draft.draft_data.lineage_is_orphan ?? false;

  const handleFamilySelect = (familyId: string) => {
    if (familyId === 'orphan') {
      updateDraft.mutate({
        draftId: draft.id,
        data: { family_id: null, draft_data: { ...draft.draft_data, lineage_is_orphan: true } },
      });
    } else {
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          family_id: parseInt(familyId, 10),
          draft_data: { ...draft.draft_data, lineage_is_orphan: false },
        },
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
        <h2 className="theme-heading text-2xl font-bold">{copy?.lineage_heading ?? ''}</h2>
        <p className="mt-2 text-muted-foreground">{copy?.lineage_intro ?? ''}</p>
      </div>

      {/* Orphan option */}
      <Card
        className={cn(
          'max-w-md cursor-pointer transition-all',
          isOrphan && 'ring-2 ring-primary',
          !isOrphan && 'hover:ring-1 hover:ring-primary/50'
        )}
        onClick={() => handleFamilySelect('orphan')}
      >
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Orphan / No Family</CardTitle>
            </div>
            <span role="presentation" onClick={(e) => e.stopPropagation()}>
              <Switch
                checked={isOrphan}
                onCheckedChange={(checked) => {
                  if (checked) {
                    handleFamilySelect('orphan');
                  } else {
                    updateDraft.mutate({
                      draftId: draft.id,
                      data: {
                        draft_data: { ...draft.draft_data, lineage_is_orphan: false },
                      },
                    });
                  }
                }}
              />
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <CardDescription>
            Your character has no known family, or has been disowned.
          </CardDescription>
        </CardContent>
      </Card>

      {/* Tarot naming ritual for orphans */}
      {isOrphan && <TarotNamingRitual draft={draft} />}

      {/* Family selection (disabled if orphan selected) */}
      {!isOrphan && (
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

          {draft.family && <KinSlotPicker draft={draft} familyId={draft.family.id} />}

          {!draft.family && <HouseFoundingPanel draft={draft} />}
        </section>
      )}
    </motion.div>
  );
}

// =============================================================================
// HouseFoundingPanel — define the house behind a set-aside title (#1884 Phase D)
// =============================================================================

const PRINCIPLE_AXES = ['mercy', 'method', 'status', 'change', 'allegiance', 'power'] as const;

function HouseFoundingPanel({ draft }: { draft: CharacterDraft }) {
  const queryClient = useQueryClient();
  const { data: titles = [] } = useClaimableTitles();
  const { data: claim } = useHouseClaim(draft.id);
  const [titleId, setTitleId] = useState<number | null>(null);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [houseName, setHouseName] = useState('');
  const [backstory, setBackstory] = useState('');
  const [words, setWords] = useState('');
  const [colors, setColors] = useState('');
  const [sigil, setSigil] = useState('');
  const [lands, setLands] = useState('');
  const [aspectPicks, setAspectPicks] = useState<Record<number, number[]>>({});
  const [principles, setPrinciples] = useState<Record<string, number>>(
    Object.fromEntries(PRINCIPLE_AXES.map((axis) => [axis, 0]))
  );

  const toggleAspectOption = (definitionId: number, optionId: number, maxPicks: number) => {
    setAspectPicks((prev) => {
      const current = prev[definitionId] ?? [];
      if (current.includes(optionId)) {
        return { ...prev, [definitionId]: current.filter((id) => id !== optionId) };
      }
      if (maxPicks === 1) {
        return { ...prev, [definitionId]: [optionId] };
      }
      if (current.length >= maxPicks) {
        return prev;
      }
      return { ...prev, [definitionId]: [...current, optionId] };
    });
  };

  const submit = useMutation({
    mutationFn: (payload: HouseClaimPayload) => submitHouseClaim(draft.id, payload),
    onSuccess: () => {
      toast.success('House claim filed — staff will review it with your application.');
      void queryClient.invalidateQueries({
        queryKey: ['character-creation', 'house-claim', draft.id],
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (claim) {
    return (
      <div className="space-y-1 rounded-md border p-3">
        <Label className="text-sm font-medium text-muted-foreground">Your House Claim</Label>
        <p className="text-sm">
          House {claim.house_name} — {claim.title_name}{' '}
          <Badge variant={claim.status === 'rejected' ? 'destructive' : 'secondary'}>
            {claim.status}
          </Badge>
        </p>
        {claim.review_note && <p className="text-xs text-muted-foreground">{claim.review_note}</p>}
      </div>
    );
  }
  if (titles.length === 0) {
    return null;
  }

  const selectedTitle: ClaimableTitle | undefined = titles.find((t) => t.id === titleId);
  const templates = selectedTitle?.templates ?? [];
  const selectedTemplate = templates.find((t) => t.id === templateId);

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div>
        <Label className="text-sm font-medium text-muted-foreground">Define a House</Label>
        <p className="text-xs text-muted-foreground">
          Enter play as the representative of a house that has always held one of these set-aside
          titles. Your backstory must match; staff reviews the claim with your application.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Select
          value={titleId ? String(titleId) : ''}
          onValueChange={(value) => {
            setTitleId(Number(value));
            setTemplateId(null);
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Choose a vacant title" />
          </SelectTrigger>
          <SelectContent>
            {titles.map((title) => (
              <SelectItem key={title.id} value={String(title.id)}>
                {title.name} ({title.realm_name})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={templateId ? String(templateId) : ''}
          onValueChange={(value) => setTemplateId(Number(value))}
          disabled={!selectedTitle}
        >
          <SelectTrigger>
            <SelectValue placeholder="Charter template" />
          </SelectTrigger>
          <SelectContent>
            {templates.map((template) => (
              <SelectItem key={template.id} value={String(template.id)}>
                {template.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selectedTemplate && (
        <>
          {selectedTemplate.features.length > 0 && (
            <div className="space-y-1 rounded-md border bg-muted/30 p-2">
              <Label className="text-xs font-medium text-muted-foreground">
                A house of this charter
              </Label>
              {selectedTemplate.features.map((feature) => (
                <p key={feature.id} className="text-xs">
                  <span className="font-medium">{feature.name}</span> — {feature.description}
                </p>
              ))}
            </div>
          )}
          <Input
            placeholder="House name (family surname)"
            value={houseName}
            onChange={(event) => setHouseName(event.target.value)}
          />
          <Textarea
            placeholder="The house as it has always been — its lands, its temper, its debts."
            value={backstory}
            onChange={(event) => setBackstory(event.target.value)}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              placeholder='House words ("The Debt Is Kept")'
              value={words}
              onChange={(event) => setWords(event.target.value)}
            />
            <Input
              placeholder="House colors (oxblood and slate)"
              value={colors}
              onChange={(event) => setColors(event.target.value)}
            />
          </div>
          <Textarea
            placeholder="The sigil, described."
            value={sigil}
            onChange={(event) => setSigil(event.target.value)}
          />
          {selectedTitle?.seat_domain_name ? (
            <Textarea
              placeholder={`The lands of ${selectedTitle.seat_domain_name}, described.`}
              value={lands}
              onChange={(event) => setLands(event.target.value)}
            />
          ) : null}
          {selectedTemplate.aspect_definitions.map((definition) => {
            const picked = aspectPicks[definition.id] ?? [];
            const maxPicks = definition.max_picks ?? 1;
            return (
              <div key={definition.id} className="space-y-1">
                <Label className="text-sm font-medium">
                  {definition.name}
                  {maxPicks > 1 && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      ({picked.length}/{maxPicks})
                    </span>
                  )}
                </Label>
                <p className="text-xs text-muted-foreground">{definition.prompt}</p>
                <div className="grid gap-1 sm:grid-cols-2">
                  {definition.options.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => toggleAspectOption(definition.id, option.id, maxPicks)}
                      className={`rounded-md border p-2 text-left text-xs transition-colors ${
                        picked.includes(option.id)
                          ? 'border-primary bg-primary/10'
                          : 'hover:bg-muted/50'
                      }`}
                    >
                      <span className="font-medium">{option.name}</span>
                      {option.description && (
                        <span className="block text-muted-foreground">{option.description}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          <div className="grid grid-cols-3 gap-2">
            {PRINCIPLE_AXES.map((axis) => (
              <div key={axis}>
                <Label className="text-xs capitalize text-muted-foreground">{axis}</Label>
                <Input
                  type="number"
                  min={-5}
                  max={5}
                  value={principles[axis]}
                  onChange={(event) =>
                    setPrinciples((prev) => ({ ...prev, [axis]: Number(event.target.value) }))
                  }
                />
              </div>
            ))}
          </div>
          <Button
            size="sm"
            disabled={
              !houseName ||
              !backstory ||
              !words ||
              !colors ||
              !sigil ||
              (!!selectedTitle?.seat_domain_name && !lands) ||
              !selectedTemplate.aspect_definitions.every((definition) => {
                const count = (aspectPicks[definition.id] ?? []).length;
                return count >= (definition.min_picks ?? 1) && count <= (definition.max_picks ?? 1);
              }) ||
              submit.isPending
            }
            onClick={() =>
              submit.mutate({
                title: titleId!,
                template: templateId!,
                house_name: houseName,
                backstory,
                words,
                colors,
                sigil_description: sigil,
                lands_writeup: lands,
                aspects: selectedTemplate.aspect_definitions.map((definition) => ({
                  definition: definition.id,
                  options: aspectPicks[definition.id] ?? [],
                })),
                mercy: principles.mercy,
                method: principles.method,
                status: principles.status,
                change: principles.change,
                allegiance: principles.allegiance,
                power: principles.power,
              })
            }
          >
            File the Claim
          </Button>
        </>
      )}
    </div>
  );
}

// =============================================================================
// KinSlotPicker — open app-in positions for the chosen family (#2062)
// =============================================================================

interface KinSlotPickerProps {
  draft: CharacterDraft;
  familyId: number;
}

function KinSlotPicker({ draft, familyId }: KinSlotPickerProps) {
  const updateDraft = useUpdateDraft();
  const { data: openings, isLoading } = useFamilySlots(familyId);

  if (isLoading) {
    return <div className="h-10 animate-pulse rounded bg-muted" />;
  }
  const slots = openings?.slots ?? [];
  const pools = openings?.pools ?? [];
  if (slots.length === 0 && pools.length === 0) {
    return null;
  }

  const selectedSlotId = draft.claimed_kin_slot ?? null;
  const selectedPoolId = draft.claimed_kin_pool ?? null;

  const pick = (slot: KinSlot | null, pool: KinSlotPool | null) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        claimed_kin_slot_id: slot ? slot.id : null,
        claimed_kin_pool_id: pool ? pool.id : null,
      },
    });
  };

  const constraintLine = (item: {
    age_min: number | null;
    age_max: number | null;
    allowed_genders: string[];
  }) => {
    const parts: string[] = [];
    if (item.age_min !== null || item.age_max !== null) {
      parts.push(`age ${item.age_min ?? '?'}–${item.age_max ?? '?'}`);
    }
    if (item.allowed_genders.length > 0) {
      parts.push(item.allowed_genders.join('/'));
    }
    return parts.join(' · ');
  };

  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium text-muted-foreground">
        Open Positions in This House
      </Label>
      <p className="text-xs text-muted-foreground">
        Claim a pre-authored position to inherit a living family tree, or take none and stand apart.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Card
          className={cn(
            'cursor-pointer transition-all',
            !selectedSlotId && !selectedPoolId && 'ring-2 ring-primary'
          )}
          onClick={() => pick(null, null)}
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">No specific position</CardTitle>
          </CardHeader>
        </Card>
        {slots.map((slot) => (
          <Card
            key={`slot-${slot.id}`}
            className={cn(
              'cursor-pointer transition-all',
              selectedSlotId === slot.id && 'ring-2 ring-primary'
            )}
            onClick={() => pick(slot, null)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                {slot.name || 'Unnamed position'}
                {slot.name_locked ? ' (name set)' : ''}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-xs text-muted-foreground">
              {slot.description || 'A pre-authored place in the family tree.'}
              {constraintLine(slot) && <div className="mt-1">{constraintLine(slot)}</div>}
            </CardContent>
          </Card>
        ))}
        {pools.map((pool) => (
          <Card
            key={`pool-${pool.id}`}
            className={cn(
              'cursor-pointer transition-all',
              selectedPoolId === pool.id && 'ring-2 ring-primary'
            )}
            onClick={() => pick(null, pool)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                {pool.description || 'Family opening'} ({pool.count_remaining} left)
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-xs text-muted-foreground">
              {pool.parent_names.length > 0 && (
                <span>Child of {pool.parent_names.join(' & ')}</span>
              )}
              {constraintLine(pool) && <div className="mt-1">{constraintLine(pool)}</div>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
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
  const { data: ritualConfig } = useNamingRitualConfig();

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
          {ritualConfig?.codex_entry_id ? (
            <CodexTerm entryId={ritualConfig.codex_entry_id}>
              {ritualConfig?.flavor_text ??
                'A Mirrormask draws from the Arcana to divine your name...'}
            </CodexTerm>
          ) : (
            (ritualConfig?.flavor_text ??
            'A Mirrormask draws from the Arcana to divine your name...')
          )}
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
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-muted-foreground">Minor Arcana</h4>
          {selectedCardName !== null && (
            <div className="flex items-center gap-2">
              <Label htmlFor="tarot-orientation-minor" className="text-xs">
                Upright
              </Label>
              <Switch
                id="tarot-orientation-minor"
                checked={isReversed}
                onCheckedChange={handleToggleReversed}
              />
              <Label htmlFor="tarot-orientation-minor" className="text-xs">
                Reversed
              </Label>
            </div>
          )}
        </div>
        {(Object.entries(minorBySuit) as [string, TarotCard[]][]).map(([suit, suitCards]) => {
          if (suitCards.length === 0) return null;
          const suitSurname = suitCards[0]
            ? getSurname(suitCards[0], isReversed)
            : suit.charAt(0).toUpperCase() + suit.slice(1);
          return (
            <div key={suit} className="space-y-2">
              <div className="flex items-center gap-2">
                <Label className="text-sm font-medium capitalize">{suit}</Label>
                <span className="text-xs text-muted-foreground">(Surname: {suitSurname})</span>
              </div>
              <div className="grid gap-1.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {suitCards.map((card) => {
                  const showReversed = isReversed && card.description_reversed;
                  const minorDesc = showReversed ? card.description_reversed : card.description;
                  const cardElement = (
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
                  );

                  if (minorDesc) {
                    return (
                      <HoverCard key={card.id} openDelay={200}>
                        <HoverCardTrigger asChild>{cardElement}</HoverCardTrigger>
                        <HoverCardContent className="w-60">
                          <p className="mb-1 text-xs font-semibold text-muted-foreground">
                            {showReversed ? 'Reversed' : 'Upright'}
                          </p>
                          <p className="text-sm">{minorDesc}</p>
                        </HoverCardContent>
                      </HoverCard>
                    );
                  }

                  return cardElement;
                })}
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

  const description =
    isSelected && isReversed && card.description_reversed
      ? card.description_reversed
      : card.description;

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
      {description && (
        <CardContent className="px-3 pb-3 pt-0">
          <CardDescription className="line-clamp-2 text-xs">{description}</CardDescription>
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
