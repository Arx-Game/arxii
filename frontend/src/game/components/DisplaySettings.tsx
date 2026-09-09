import { useEffect } from 'react';
import { usePlayPreferences } from '../playPreferences';

/** Small first-release typography controls; layout editors remain deferred. */
export function DisplaySettings() {
  const { preferences, update } = usePlayPreferences();
  useEffect(() => {
    document.documentElement.style.setProperty('--play-prose-size', `${preferences.proseSize}px`);
    document.documentElement.style.setProperty(
      '--play-reading-measure',
      `${preferences.measure}ch`
    );
    document.documentElement.style.setProperty(
      '--play-prose-family',
      preferences.proseFamily === 'serif'
        ? 'ui-serif, Georgia, serif'
        : 'ui-sans-serif, system-ui, sans-serif'
    );
  }, [preferences]);
  return (
    <details className="rounded border px-2 py-1 text-xs">
      <summary className="cursor-pointer font-medium">Display settings</summary>
      <div className="mt-2 space-y-2 pb-1">
        <label className="flex items-center justify-between gap-2">
          Text size{' '}
          <input
            aria-label="Prose text size"
            type="range"
            min="12"
            max="20"
            value={preferences.proseSize}
            onChange={(event) => update({ proseSize: Number(event.target.value) })}
          />
        </label>
        <label className="flex items-center justify-between gap-2">
          Measure{' '}
          <input
            aria-label="Reading measure"
            type="range"
            min="72"
            max="110"
            value={preferences.measure}
            onChange={(event) => update({ measure: Number(event.target.value) })}
          />
        </label>
        <label className="flex items-center justify-between gap-2">
          Font{' '}
          <select
            aria-label="Prose font"
            value={preferences.proseFamily}
            onChange={(event) => update({ proseFamily: event.target.value as 'sans' | 'serif' })}
          >
            <option value="sans">Sans</option>
            <option value="serif">Serif</option>
          </select>
        </label>
      </div>
    </details>
  );
}
