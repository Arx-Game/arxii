/**
 * A colour choice (#5241): one swatch per option on a row, one pressed.
 *
 * A colour's name alone does not say which red it is (owner ruling 2026-11-21: "a
 * color prism for comparison of what color we are talking about"), so each option
 * is drawn in its own colour and names itself on hover and to a screen reader. The
 * row prints no names; the caller prints the chosen one beside the feature's name,
 * and `onPreview` hands it the name under the pointer or the focus.
 *
 * An option with no colour value (not set yet, or no single colour: Prismatic,
 * Mismatched) is drawn striped, so it is still a swatch and still told apart.
 */
import type { CSSProperties } from 'react';

interface SwatchOption<T extends string | number> {
  value: T;
  label: string;
  /** `#rrggbb`, or blank for an option with no single colour. */
  hex: string;
  /** Outside the ordinary list (#3739): drawn with a dashed edge. Styling only. */
  beyond?: boolean;
}

interface SwatchRowProps<T extends string | number> {
  /** The id of the element that names the group. */
  labelledBy: string;
  options: SwatchOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
  /** Pressing the chosen swatch again clears it. */
  clearable?: boolean;
  /** The name under the pointer or the focus, null when there is none. */
  onPreview?: (label: string | null) => void;
}

// The value goes into a style, so it is checked here as well as on the server.
const HEX = /^#[0-9a-fA-F]{6}$/;

export function SwatchRow<T extends string | number>({
  labelledBy,
  options,
  value,
  onChange,
  clearable,
  onPreview,
}: SwatchRowProps<T>) {
  return (
    <div className="swatch-row" role="group" aria-labelledby={labelledBy}>
      {options.map((opt) => {
        const pressed = value === opt.value;
        const hasHue = HEX.test(opt.hex);
        const classes = ['swatch', hasHue ? '' : 'no-hue', opt.beyond ? 'beyond' : '']
          .filter(Boolean)
          .join(' ');
        return (
          <button
            key={String(opt.value)}
            type="button"
            className={classes}
            aria-pressed={pressed}
            aria-label={opt.label}
            title={opt.label}
            style={hasHue ? ({ '--swatch': opt.hex } as CSSProperties) : undefined}
            onMouseEnter={() => onPreview?.(opt.label)}
            onMouseLeave={() => onPreview?.(null)}
            onFocus={() => onPreview?.(opt.label)}
            onBlur={() => onPreview?.(null)}
            onClick={() => {
              if (pressed) {
                if (clearable) onChange(null);
                return;
              }
              onChange(opt.value);
            }}
          />
        );
      })}
    </div>
  );
}
