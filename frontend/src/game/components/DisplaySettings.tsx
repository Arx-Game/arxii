import { useEffect } from 'react';
import type { PlayPreferences } from '../playPreferences';
import { usePlayPreferences } from '../playPreferences';

interface DisplaySettingsProps {
  accountId?: number | null;
}

/** Compact account-scoped controls for the narrative workspace. */
export function DisplaySettings({ accountId }: DisplaySettingsProps) {
  const { preferences, update, storageWarning } = usePlayPreferences(accountId);
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
    document.documentElement.dataset.playDensity = preferences.density;
    document.documentElement.style.setProperty(
      '--play-density-gap',
      preferences.density === 'comfortable' ? '1.25rem' : '0.75rem'
    );
    window.dispatchEvent(new CustomEvent('arx-play-preferences', { detail: preferences }));
  }, [preferences]);
  return (
    <details className="rounded border px-2 py-1 text-xs">
      <summary className="cursor-pointer font-medium">Display settings</summary>
      <div className="mt-2 space-y-2 pb-1">
        {storageWarning && (
          <p className="rounded bg-muted px-2 py-1 text-muted-foreground" role="status">
            Preferences are active for this tab but could not be saved in this browser.
          </p>
        )}
        <label className="flex min-h-11 items-center justify-between gap-2">
          Text size{' '}
          <input
            aria-label="Prose text size"
            className="h-11"
            type="range"
            min="12"
            max="20"
            value={preferences.proseSize}
            onChange={(event) => update({ proseSize: Number(event.target.value) })}
          />
        </label>
        <label className="flex min-h-11 items-center justify-between gap-2">
          Measure{' '}
          <input
            aria-label="Reading measure"
            className="h-11"
            type="range"
            min="72"
            max="110"
            value={preferences.measure}
            onChange={(event) => update({ measure: Number(event.target.value) })}
          />
        </label>
        <label className="flex min-h-11 items-center justify-between gap-2">
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
        <label className="flex min-h-11 items-center justify-between gap-2">
          Sidebar width{' '}
          <input
            aria-label="Sidebar width"
            className="h-11"
            type="range"
            min="240"
            max="360"
            value={preferences.sidebarWidth}
            onChange={(event) => update({ sidebarWidth: Number(event.target.value) })}
          />
        </label>
        <label className="flex min-h-11 items-center justify-between gap-2">
          Sidebar side{' '}
          <select
            aria-label="Sidebar side"
            value={preferences.sidebarSide}
            onChange={(event) =>
              update({ sidebarSide: event.target.value as PlayPreferences['sidebarSide'] })
            }
          >
            <option value="right">Right</option>
            <option value="left">Left</option>
          </select>
        </label>
        <label className="flex min-h-11 items-center justify-between gap-2">
          Density{' '}
          <select
            aria-label="Reading density"
            value={preferences.density}
            onChange={(event) =>
              update({ density: event.target.value as PlayPreferences['density'] })
            }
          >
            <option value="compact">Compact</option>
            <option value="comfortable">Comfortable</option>
          </select>
        </label>
        <label className="flex min-h-11 items-center justify-between gap-2">
          Reader{' '}
          <select
            aria-label="Reader order"
            value={preferences.readerMode}
            onChange={(event) =>
              update({ readerMode: event.target.value as PlayPreferences['readerMode'] })
            }
          >
            <option value="threads">Threads</option>
            <option value="chronological">Chronological</option>
          </select>
        </label>
      </div>
    </details>
  );
}
