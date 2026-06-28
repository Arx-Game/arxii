import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { extractErrorMessage } from '@/lib/errors';

import {
  useAlternateSelvesQuery,
  useRevertFormMutation,
  useShiftFormMutation,
  type SwitchableAlternateSelf,
} from '../formQueries';

interface FormSwitcherProps {
  characterSheetId: number;
}

function activeLabel(alt: SwitchableAlternateSelf | null): string {
  if (!alt) return 'True self';
  return alt.display_name || alt.form_name || alt.persona_name || 'Alternate self';
}

function subLabel(alt: SwitchableAlternateSelf): string {
  const parts: string[] = [];
  if (alt.form_name) parts.push(alt.form_name);
  if (alt.persona_name) parts.push(alt.persona_name);
  if (alt.has_combat_profile) parts.push('combat profile');
  if (alt.has_techniques) parts.push('techniques');
  return parts.join(' · ') || 'Alternate self';
}

/**
 * Top-bar control for the form the player is wearing (#1111 slice 4).
 *
 * Shows the active alternate self (or "True self") and lets the player shift or revert.
 * Revert is attempted on click; if blocked (e.g., rage), the server message is surfaced.
 */
export function FormSwitcher({ characterSheetId }: FormSwitcherProps) {
  const { data: alternates = [] } = useAlternateSelvesQuery(characterSheetId);
  const shift = useShiftFormMutation();
  const revert = useRevertFormMutation();
  const [open, setOpen] = useState(false);

  const worn = useMemo(() => alternates.find((alt) => alt.is_active) ?? null, [alternates]);
  const isShiftingOrReverting = shift.isPending || revert.isPending;

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger
          className="flex items-center gap-1.5 rounded px-2 py-1 text-sm font-medium ring-1 ring-primary/40 hover:bg-accent disabled:opacity-50"
          disabled={isShiftingOrReverting}
          title="Shift into an alternate self"
        >
          <span>{activeLabel(worn)}</span>
          <span className="text-xs text-muted-foreground" aria-hidden>
            ▾
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-56">
          <DropdownMenuLabel>Shift form</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={worn?.id.toString() ?? 'true-self'}
            onValueChange={(value) => {
              const id = Number(value);
              if (!worn || id !== worn.id) {
                shift.mutate(id, {
                  onSuccess: () => setOpen(false),
                });
              }
            }}
          >
            <DropdownMenuRadioItem value="true-self" className="gap-2">
              <span className="flex flex-col">
                <span>True self</span>
                <span className="text-xs text-muted-foreground">Revert to your natural form</span>
              </span>
            </DropdownMenuRadioItem>
            {alternates.map((alt) => (
              <DropdownMenuRadioItem
                key={alt.id}
                value={alt.id.toString()}
                className="gap-2"
                disabled={alt.is_active}
              >
                <span className="flex flex-col">
                  <span>{activeLabel(alt)}</span>
                  <span className="text-xs text-muted-foreground">{subLabel(alt)}</span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {worn ? (
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs"
          disabled={isShiftingOrReverting}
          onClick={() => revert.mutate(undefined)}
        >
          Revert
        </Button>
      ) : null}

      {(shift.error ?? revert.error) ? (
        <span className="text-xs text-destructive">
          {extractErrorMessage(shift.error ?? revert.error, 'Form action failed.')}
        </span>
      ) : null}
    </div>
  );
}
