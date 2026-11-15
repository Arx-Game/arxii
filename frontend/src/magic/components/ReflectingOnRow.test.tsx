/**
 * ReflectingOnRow tests (#5124): the row lists what the writer can reflect on, takes one pick
 * and Embrace or Disown, warns before replacing a waiting reflection, and offers nothing when
 * there is nothing to reflect on.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ReflectionDraft } from '@/magic/reflection';
import { NO_REFLECTION, REFLECTION_INCOMPLETE_LINE, reflectionFields } from '@/magic/reflection';
import type { ReflectionOption } from '@/magic/types';
import { ReflectingOnRow } from './ReflectingOnRow';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getReflectionOptions: vi.fn(),
}));

import * as api from '@/magic/api';

const options: ReflectionOption[] = [
  { kind: 'deed', id: 33, label: "Barred the overseers' door · 5 Wonder", replaces_waiting: false },
  {
    kind: 'resonance',
    id: 21,
    label: 'Your Domination · unsettling you',
    replaces_waiting: true,
  },
];

let latest: ReflectionDraft = NO_REFLECTION;

function Harness() {
  const [value, setValue] = useState<ReflectionDraft>(NO_REFLECTION);
  latest = value;
  return <ReflectingOnRow characterSheetId={7} value={value} onChange={setValue} />;
}

describe('ReflectingOnRow', () => {
  beforeEach(() => {
    latest = NO_REFLECTION;
    vi.mocked(api.getReflectionOptions).mockReset();
  });

  it('lists the unsettling resonance and the deeds, then asks Embrace or Disown once one is picked', async () => {
    vi.mocked(api.getReflectionOptions).mockResolvedValue(options);
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    expect(await screen.findByText("Barred the overseers' door · 5 Wonder")).toBeInTheDocument();
    expect(screen.getByText('Your Domination · unsettling you')).toBeInTheDocument();
    // The deed is drawn before the unsettling resonance, and the pair is there from the start.
    const pills = screen.getAllByTestId(/^reflect-option-/).map((el) => el.textContent);
    expect(pills).toEqual([
      "Barred the overseers' door · 5 Wonder",
      'Your Domination · unsettling you',
    ]);
    expect(screen.getByTestId('reflect-choice-EMBRACE')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('reflect-choice-DISOWN')).toHaveAttribute('aria-pressed', 'false');
    expect(reflectionFields(latest)).toEqual({});

    await user.click(screen.getByTestId('reflect-option-deed-33'));
    expect(screen.getByTestId('reflect-incomplete')).toHaveTextContent(REFLECTION_INCOMPLETE_LINE);
    expect(reflectionFields(latest)).toEqual({});
    await user.click(screen.getByTestId('reflect-choice-DISOWN'));
    expect(screen.queryByTestId('reflect-incomplete')).toBeNull();

    expect(reflectionFields(latest)).toEqual({ reflect_choice: 'DISOWN', reflect_grant_id: 33 });
    expect(screen.queryByTestId('reflect-replaces-warning')).toBeNull();
  });

  it('warns that a new reflection on the unsettling resonance replaces the waiting one, and lets the writer undo the pick', async () => {
    vi.mocked(api.getReflectionOptions).mockResolvedValue(options);
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(await screen.findByTestId('reflect-option-resonance-21'));
    await user.click(screen.getByTestId('reflect-choice-EMBRACE'));
    expect(screen.getByTestId('reflect-replaces-warning')).toBeInTheDocument();
    expect(reflectionFields(latest)).toEqual({
      reflect_choice: 'EMBRACE',
      reflect_resonance_id: 21,
    });

    await user.click(screen.getByTestId('reflect-option-resonance-21'));
    await user.click(screen.getByTestId('reflect-choice-EMBRACE'));
    expect(latest).toEqual(NO_REFLECTION);
    expect(screen.queryByTestId('reflect-replaces-warning')).toBeNull();
  });

  it('renders nothing when there is nothing to reflect on', async () => {
    vi.mocked(api.getReflectionOptions).mockResolvedValue([]);
    renderWithProviders(<Harness />);

    await vi.waitFor(() => expect(api.getReflectionOptions).toHaveBeenCalledWith(7));
    expect(screen.queryByTestId('reflecting-on-row')).toBeNull();
  });
});
