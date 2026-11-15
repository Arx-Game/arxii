/**
 * ReflectingOnRow (#5124, demo Screen 5): the optional "Reflecting on" row of a pose and of a
 * journal entry. The writer picks one thing the writing reflects on, a kindled deed or the
 * resonance unsettling them, then Embrace or Disown. Posting records the reflection and
 * changes nothing yet; the room sees only the pose, and only the writer sees this row.
 *
 * Reflecting on the unsettling resonance replaces an older reflection still waiting on it, so
 * the row says so before the writer posts. Renders nothing when there is nothing to reflect on.
 *
 * Wire contract: GET /api/magic/reflectables/ (ReflectableViewSet).
 */

import { cn } from '@/lib/utils';
import { useReflectionOptions } from '@/magic/queries';
import {
  REFLECTION_CHOICES,
  sameOption,
  type ReflectionChoice,
  type ReflectionDraft,
} from '@/magic/reflection';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the writer; null while unknown. */
  characterSheetId: number | null;
  value: ReflectionDraft | null;
  onChange: (value: ReflectionDraft | null) => void;
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
  testId?: string;
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

export function ReflectingOnRow({ characterSheetId, value, onChange, className }: Props) {
  const { data: options = [] } = useReflectionOptions(characterSheetId);
  if (options.length === 0) return null;

  const pick = (option: (typeof options)[number]) => {
    if (value !== null && sameOption(value.option, option)) {
      onChange(null);
      return;
    }
    onChange({ option, choice: value?.choice ?? 'EMBRACE' });
  };
  const choose = (choice: ReflectionChoice) => {
    if (value !== null) onChange({ ...value, choice });
  };

  return (
    <div
      className={cn('space-y-2 rounded border border-border px-3 py-2', className)}
      data-testid="reflecting-on-row"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold">Reflecting on</span>
        <span className="text-xs text-muted-foreground">optional</span>
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Reflecting on">
        {options.map((option) => (
          <Pill
            key={`${option.kind}-${option.id}`}
            pressed={value !== null && sameOption(value.option, option)}
            onClick={() => pick(option)}
            testId={`reflect-option-${option.kind}-${option.id}`}
          >
            {option.label}
          </Pill>
        ))}
      </div>
      {value !== null && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Embrace or disown">
          {REFLECTION_CHOICES.map((choice) => (
            <Pill
              key={choice.value}
              pressed={value.choice === choice.value}
              onClick={() => choose(choice.value)}
              testId={`reflect-choice-${choice.value}`}
            >
              {choice.label}
            </Pill>
          ))}
        </div>
      )}
      {value?.option.replaces_waiting && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="reflect-replaces-warning"
          role="status"
        >
          A reflection on this is already waiting. Posting this one replaces it.
        </p>
      )}
    </div>
  );
}
