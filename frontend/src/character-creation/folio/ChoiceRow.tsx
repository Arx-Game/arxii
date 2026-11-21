/** A segmented choice (#3540): a few named options on a row, one pressed. */
interface ChoiceOption<T extends string | number> {
  value: T;
  label: string;
  title?: string;
  disabled?: boolean;
}

interface ChoiceRowProps<T extends string | number> {
  label: string;
  /** When set, the group is labelled by this element instead of `label`. */
  labelledBy?: string;
  options: ChoiceOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
  /** Pressing the chosen option again clears it. */
  clearable?: boolean;
}

export function ChoiceRow<T extends string | number>({
  label,
  labelledBy,
  options,
  value,
  onChange,
  clearable,
}: ChoiceRowProps<T>) {
  return (
    <div
      className="choice-row"
      role="group"
      aria-label={labelledBy ? undefined : label}
      aria-labelledby={labelledBy}
    >
      {options.map((opt) => {
        const pressed = value === opt.value;
        return (
          <button
            key={String(opt.value)}
            type="button"
            aria-pressed={pressed}
            title={opt.title}
            disabled={opt.disabled}
            onClick={() => {
              if (pressed) {
                if (clearable) onChange(null);
                return;
              }
              onChange(opt.value);
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
