/**
 * SineatingRow tests (#5177): the row lists the pleas the writer can make or answer, takes one
 * pick and a number of units, badges a plea waiting for them and lets them decline it, and
 * offers nothing when there is nothing to make or answer.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { NO_SINEATING, sineatingFields, type SineatingDraft } from '@/magic/sineating';
import type { components } from '@/generated/api';
import { SineatingRow } from './SineatingRow';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getSineatingOptions: vi.fn(),
  declineSineating: vi.fn(),
}));

const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }));

import * as api from '@/magic/api';

type Option = components['schemas']['SineatingOption'];

const entreat: Option = {
  role: 'entreat',
  partner_sheet_id: 20,
  partner_name: 'Corvin',
  max_units: 3,
  resonance_name: 'Ruin',
};
const perform: Option = {
  role: 'perform',
  partner_sheet_id: 10,
  partner_name: 'Ysmay',
  max_units: 2,
  resonance_name: 'Ruin',
};

let latest: SineatingDraft = NO_SINEATING;

function Harness({ inScene = true }: { inScene?: boolean }) {
  const [value, setValue] = useState<SineatingDraft>(NO_SINEATING);
  latest = value;
  return <SineatingRow characterSheetId={7} inScene={inScene} value={value} onChange={setValue} />;
}

describe('SineatingRow', () => {
  beforeEach(() => {
    latest = NO_SINEATING;
    vi.mocked(api.getSineatingOptions).mockReset();
    vi.mocked(api.declineSineating).mockReset();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it('names who is asked and whose sins are taken on, and sends the three fields once one is picked', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([entreat, perform]);
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    expect(await screen.findByText(/Ask Corvin to take on your sins/)).toBeInTheDocument();
    expect(screen.getByText(/Take on Ysmay's sins/)).toBeInTheDocument();
    expect(sineatingFields(latest)).toEqual({});

    await user.click(screen.getByTestId('sineating-option-entreat-20'));
    // The writer starts at everything the plea allows and can lower it.
    expect(sineatingFields(latest)).toEqual({
      sineating_role: 'entreat',
      sineating_partner_id: 20,
      sineating_units: 3,
    });
    await user.click(screen.getByTestId('sineating-units-2'));
    expect(sineatingFields(latest).sineating_units).toBe(2);

    await user.click(screen.getByTestId('sineating-option-entreat-20'));
    expect(latest).toEqual(NO_SINEATING);
  });

  it('badges a plea waiting for the writer and sends the ritual when they answer it', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([perform]);
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    expect(await screen.findByTestId('sineating-plea-waiting')).toHaveTextContent('Plea waiting');
    await user.click(screen.getByTestId('sineating-option-perform-10'));
    expect(sineatingFields(latest)).toEqual({
      sineating_role: 'perform',
      sineating_partner_id: 10,
      sineating_units: 2,
    });
  });

  it('declines a waiting plea for the writer and drops the pick', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([perform]);
    vi.mocked(api.declineSineating).mockResolvedValue({ detail: "You decline Ysmay's plea." });
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(await screen.findByTestId('sineating-option-perform-10'));
    await user.click(screen.getByTestId('sineating-decline-10'));

    await waitFor(() =>
      expect(api.declineSineating).toHaveBeenCalledWith({ actor_sheet_id: 7, sinner_sheet_id: 10 })
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("You decline Ysmay's plea."));
    expect(latest).toEqual(NO_SINEATING);
  });

  it('shows the refusal when a plea cannot be declined', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([perform]);
    vi.mocked(api.declineSineating).mockRejectedValue(new Error('No plea from Ysmay is waiting.'));
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(await screen.findByTestId('sineating-decline-10'));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('No plea from Ysmay is waiting.'));
  });

  it('renders nothing when there is nothing to make or answer', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([]);
    renderWithProviders(<Harness />);

    await waitFor(() => expect(api.getSineatingOptions).toHaveBeenCalledWith(7));
    expect(screen.queryByTestId('sineating-row')).toBeNull();
  });

  it('asks for nothing and renders nothing outside an active scene', async () => {
    vi.mocked(api.getSineatingOptions).mockResolvedValue([entreat]);
    renderWithProviders(<Harness inScene={false} />);

    expect(screen.queryByTestId('sineating-row')).toBeNull();
    expect(api.getSineatingOptions).not.toHaveBeenCalled();
  });
});
