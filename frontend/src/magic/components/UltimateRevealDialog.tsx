/**
 * UltimateRevealDialog — the Audere ultimate reveal and choice (#4098,
 * Screens 2-3 of the plan's demo; Screen 4 for a Crossing reveal).
 *
 * Renders one section per UltimateRevealGroup (owned/patron/companion
 * source), each a responsive grid of cards: known (solid fuchsia border,
 * shown by name), undiscovered category (dashed border, shown by its
 * evocative label only — never the raw category value), or upgrade (amber
 * border, shown by name with its prerequisite named). The player selects one
 * card, then confirms with "Choose"; after a successful choice the dialog
 * swaps to the Screen 3 chosen-ultimate card.
 *
 * Chrome follows `reveal.ceremony`: fuchsia + Flame for a plain Audere,
 * amber + DoorOpen (the same Majora tokens as AudereMajoraOfferDialog) for
 * `audere_majora` — a Crossing reveal.
 */

import { useState } from 'react';
import { DoorOpen, Flame } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ReadiedUltimate, UltimateReveal, UltimateRevealCard } from '@/magic/types';

interface UltimateRevealDialogProps {
  reveal: UltimateReveal;
  /** Set once a choice has landed — replaces the body with the Screen 3 card. */
  readied: ReadiedUltimate | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChoose: (choiceKey: string) => void;
  isPending: boolean;
  /** When set, renders a role="alert" failure line above the footer. */
  errorMessage?: string | null;
}

// The generated schema types `source` as a plain `string` (drf-spectacular
// doesn't carry the backend TextChoices as a literal enum here), but
// `UltimateSource` (src/world/magic/constants.py) has exactly these three
// members — narrowed locally so the switch below is exhaustive and a fourth
// value fails loudly instead of falling through a silent `default` (fix
// round 1 item 3).
type GroupSource = 'owned' | 'patron' | 'companion' | 'gift';

function assertNeverGroupSource(source: never): never {
  throw new Error(`Unknown UltimateRevealGroup source: ${String(source)}`);
}

function groupHeading(group: UltimateReveal['groups'][number]): string {
  switch (group.source as GroupSource) {
    case 'owned':
      return `Owned · ${group.path_name}, ${group.gift_name}`;
    case 'patron':
      return `Bond · ${group.being_name} (patron)`;
    case 'companion':
      return `Bond · ${group.companion_name} (companion)`;
    case 'gift':
      return `Gift · ${group.gift_name}`;
    default:
      return assertNeverGroupSource(group.source as never);
  }
}

function cardTitle(card: UltimateRevealCard): string {
  // Known/upgrade cards are shown by their revealed name; a category card
  // (still undiscovered) shows only its authored evocative label — never
  // the raw category value (sword/shield/crown).
  return card.kind === 'category' ? card.label : card.name;
}

function cardSubline(card: UltimateRevealCard): string {
  if (card.kind === 'known') return `known · ${card.description}`;
  if (card.kind === 'upgrade') return `upgrade of ${card.upgrade_of_name}`;
  return 'undiscovered';
}

function cardBorderClass(card: UltimateRevealCard): string {
  if (card.kind === 'known') return 'border-fuchsia-500/60 bg-fuchsia-950/20';
  if (card.kind === 'upgrade') return 'border-amber-500/60 bg-amber-950/20';
  return 'border-dashed border-border bg-muted/20';
}

export function UltimateRevealDialog({
  reveal,
  readied,
  open,
  onOpenChange,
  onChoose,
  isPending,
  errorMessage = null,
}: UltimateRevealDialogProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const isMajora = reveal.ceremony === 'audere_majora';
  const chrome = isMajora
    ? {
        border: 'border-amber-500/60',
        shadow: 'shadow-amber-500/50',
        title: 'text-amber-400',
        Icon: DoorOpen,
      }
    : {
        border: 'border-fuchsia-500/60',
        shadow: 'shadow-fuchsia-500/50',
        title: 'text-fuchsia-400',
        Icon: Flame,
      };
  const { Icon } = chrome;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        data-testid="ultimate-reveal-dialog"
        className={cn(
          'max-h-[90vh] overflow-y-auto shadow-[0_0_60px_-12px]',
          chrome.border,
          chrome.shadow
        )}
      >
        <AlertDialogHeader>
          <AlertDialogTitle
            className={cn('flex items-center gap-2 text-2xl font-bold tracking-wide', chrome.title)}
          >
            <Icon className="h-7 w-7" />
            Ultimates
          </AlertDialogTitle>
          {reveal.framing_text ? (
            <AlertDialogDescription className="text-base">
              {reveal.framing_text}
            </AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>

        {readied ? (
          <div
            className="rounded-md border border-fuchsia-500/60 bg-fuchsia-950/20 p-4"
            data-testid="ultimate-chosen-card"
          >
            <div className="text-lg font-bold text-fuchsia-300">{readied.name}</div>
            <div className="mt-0.5 text-sm text-muted-foreground">{readied.label}</div>
            <p className="mt-2 text-sm">{readied.description}</p>
          </div>
        ) : (
          <div className="space-y-5">
            {reveal.groups.map((group, groupIndex) => (
              <div key={`${group.source}-${groupIndex}`}>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {groupHeading(group)}
                </h4>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {group.cards.map((card) => {
                    const selected = selectedKey === card.choice_key;
                    return (
                      <button
                        key={card.choice_key}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => setSelectedKey(card.choice_key)}
                        disabled={isPending}
                        className={cn(
                          'rounded-md border p-3 text-left text-sm transition-colors',
                          cardBorderClass(card),
                          selected ? 'ring-2 ring-fuchsia-400' : null
                        )}
                      >
                        <div className="font-semibold">{cardTitle(card)}</div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {cardSubline(card)}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {errorMessage ? (
          <div
            role="alert"
            data-testid="ultimate-choose-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {errorMessage}
          </div>
        ) : null}

        <AlertDialogFooter>
          {readied ? (
            <Button
              className="bg-fuchsia-600 text-white hover:bg-fuchsia-500"
              onClick={() => onOpenChange(false)}
            >
              To the fight
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
                Not yet
              </Button>
              <Button
                className="bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                onClick={() => selectedKey && onChoose(selectedKey)}
                disabled={!selectedKey || isPending}
              >
                Choose
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
