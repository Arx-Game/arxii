import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { DisplaySettings } from './DisplaySettings';
import { loadPlayPreferences } from '../playPreferences';

/** The width cap the readers' column reads (`max-w-[var(--play-reading-measure,none)]`). */
function readingMeasure(): string {
  return document.documentElement.style.getPropertyValue('--play-reading-measure');
}

describe('DisplaySettings line length', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.removeProperty('--play-reading-measure');
  });

  it('lets the text fill the story pane by default', () => {
    render(<DisplaySettings accountId={1} />);

    expect(readingMeasure()).toBe('none');
    expect(screen.getByLabelText('Line length')).toHaveValue('full');
    expect(screen.queryByLabelText('Reading measure')).not.toBeInTheDocument();
  });

  it('caps the column at the measure once the player limits it', async () => {
    const user = userEvent.setup();
    render(<DisplaySettings accountId={1} />);

    await user.selectOptions(screen.getByLabelText('Line length'), 'limited');

    expect(readingMeasure()).toBe('90ch');
    expect(loadPlayPreferences(1).limitMeasure).toBe(true);

    fireEvent.change(screen.getByLabelText('Reading measure'), { target: { value: '100' } });
    expect(readingMeasure()).toBe('100ch');
  });

  it('treats preferences stored before the choice existed as full width', () => {
    localStorage.setItem(
      'arx:play-preferences:v2:account:1',
      JSON.stringify({ proseSize: 16, measure: 90 })
    );

    render(<DisplaySettings accountId={1} />);

    expect(readingMeasure()).toBe('none');
  });
});
