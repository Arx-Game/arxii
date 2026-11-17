/**
 * SineatingRow (#5177): the optional "Sineating" row of a pose. The writer picks a plea to
 * make to a Sineater who is here ("Ask Corvin to take on your sins") or a plea waiting for
 * them to answer ("Take on Ysmay's sins"), and how many units. Posting sends the pose with
 * the plea or the ritual attached; the others present see only the pose.
 *
 * A plea waiting for the writer is badged on the row, and the writer may Decline it.
 * Renders nothing when there is nothing to make or answer.
 *
 * Wire contract: GET /api/magic/sineating-options/ (SineatingOptionViewSet), polled;
 * POST /api/magic/soul-tether/sineating/decline/.
 */

import { useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDeclineSineating, useSineatingOptions } from '@/magic/queries';
import {
  NO_SINEATING,
  pickSineating,
  sameSineatingOption,
  sineatingOptionLabel,
  type SineatingDraft,
  type SineatingOption,
} from '@/magic/sineating';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the writer; null while unknown. */
  characterSheetId: number | null;
  /** Whether the writer is in an active scene; the plea and the ritual need one. */
  inScene: boolean;
  value: SineatingDraft;
  onChange: (value: SineatingDraft) => void;
  className?: string;
}

function Pill({
  pressed,
  onClick,
  testId,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      data-testid={testId}
      className={cn(
        'min-h-8 cursor-pointer rounded-full border px-3 py-1 text-xs',
        pressed
          ? 'border-foreground bg-foreground text-background'
          : 'border-border bg-transparent text-foreground hover:bg-accent'
      )}
    >
      {children}
    </button>
  );
}

function optionKey(option: SineatingOption): string {
  return `${option.role}-${option.partner_sheet_id}`;
}

export function SineatingRow({ characterSheetId, inScene, value, onChange, className }: Props) {
  const { data: options = [] } = useSineatingOptions(characterSheetId, inScene);
  const decline = useDeclineSineating();

  // A plea that is no longer here (answered, declined, its Sinner gone) leaves the pick too.
  const picked = value.option;
  const stillHere =
    picked === null || options.some((option) => sameSineatingOption(option, picked));
  useEffect(() => {
    if (!stillHere) onChange(NO_SINEATING);
  }, [stillHere, onChange]);

  if (!inScene || options.length === 0) return null;

  const waiting = options.some((option) => option.role === 'perform');
  const onDecline = (option: SineatingOption) => {
    if (characterSheetId === null) return;
    decline.mutate(
      { actor_sheet_id: characterSheetId, sinner_sheet_id: option.partner_sheet_id },
      {
        onSuccess: (result) => {
          toast.success(result.detail);
          if (picked !== null && sameSineatingOption(picked, option)) onChange(NO_SINEATING);
        },
        onError: (error) => toast.error(error.message),
      }
    );
  };

  return (
    <div
      className={cn(
        'space-y-2 rounded border px-3 py-2',
        waiting ? 'border-violet-500/60' : 'border-border',
        className
      )}
      data-testid="sineating-row"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold">Sineating</span>
        {waiting ? (
          <span
            className="rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-700 dark:text-violet-300"
            data-testid="sineating-plea-waiting"
          >
            Plea waiting
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">optional</span>
        )}
      </div>
      <div className="flex flex-col gap-1.5" role="group" aria-label="Sineating">
        {options.map((option) => {
          const pressed = picked !== null && sameSineatingOption(picked, option);
          return (
            <div key={optionKey(option)} className="flex flex-wrap items-center gap-1.5">
              <Pill
                pressed={pressed}
                onClick={() => onChange(pickSineating(value, option))}
                testId={`sineating-option-${optionKey(option)}`}
              >
                {sineatingOptionLabel(option)}
                <span className={pressed ? 'opacity-80' : 'text-muted-foreground'}>
                  {` · ${option.resonance_name}`}
                </span>
              </Pill>
              {option.role === 'perform' ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={decline.isPending}
                  onClick={() => onDecline(option)}
                  data-testid={`sineating-decline-${option.partner_sheet_id}`}
                >
                  Decline
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>
      {picked !== null ? (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Units">
          <span className="text-xs">Units</span>
          {Array.from({ length: picked.max_units }, (_, index) => index + 1).map((units) => (
            <Pill
              key={units}
              pressed={value.units === units}
              onClick={() => onChange({ ...value, units })}
              testId={`sineating-units-${units}`}
            >
              {units}
            </Pill>
          ))}
        </div>
      ) : null}
    </div>
  );
}
