/**
 * ManifestPickerPanel tests (#4341): the technique picker. Real query hooks over a
 * mocked API module, so the dispatch's `success: false` refusal path is the real one.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ManifestChoice } from '@/magic/types';
import { ManifestPickerPanel } from './ManifestPickerPanel';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getManifestChoices: vi.fn(),
  setManifestChoice: vi.fn(),
}));

import * as api from '@/magic/api';

const SHEET_ID = 7;

function choice(chosen: number | null): ManifestChoice {
  return {
    technique_id: 11,
    technique_name: 'Summon',
    chosen_option_id: chosen,
    options: [
      {
        option_id: 21,
        label: 'Hesk (your patron)',
        available: true,
        reason: '',
        companion_id: null,
      },
      {
        option_id: 22,
        label: 'Wolf',
        available: false,
        reason: 'you have no Wolf companion',
        companion_id: null,
      },
    ],
  };
}

describe('ManifestPickerPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getManifestChoices).mockReset();
    vi.mocked(api.setManifestChoice).mockReset();
  });

  it('shows each technique with its options, the unavailable one disabled with why', async () => {
    vi.mocked(api.getManifestChoices).mockResolvedValue([choice(21)]);
    renderWithProviders(<ManifestPickerPanel characterSheetId={SHEET_ID} />);

    expect(await screen.findByText('Technique: Summon')).toBeInTheDocument();
    expect(screen.getByText('Brings into a fight:')).toBeInTheDocument();
    const hesk = screen.getByRole('button', { name: 'Hesk (your patron)' });
    expect(hesk).toHaveAttribute('aria-pressed', 'true');
    const wolf = screen.getByRole('button', { name: 'Wolf (you have no Wolf companion)' });
    expect(wolf).toBeDisabled();
    expect(
      screen.getByText('Only options whose bond holds can be chosen; the others show why not.')
    ).toBeInTheDocument();
    expect(api.getManifestChoices).toHaveBeenCalledWith(SHEET_ID);
  });

  it('dispatches the pick as the character and refetches the choices', async () => {
    vi.mocked(api.getManifestChoices).mockResolvedValueOnce([choice(null)]);
    vi.mocked(api.getManifestChoices).mockResolvedValue([choice(21)]);
    vi.mocked(api.setManifestChoice).mockResolvedValue({
      message: 'Summon will bring Hesk into a fight.',
      success: true,
    });
    renderWithProviders(<ManifestPickerPanel characterSheetId={SHEET_ID} />);

    const hesk = await screen.findByRole('button', { name: 'Hesk (your patron)' });
    expect(hesk).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(hesk);

    expect(api.setManifestChoice).toHaveBeenCalledWith(SHEET_ID, 11, 21);
    expect(
      await screen.findByRole('button', { name: 'Hesk (your patron)', pressed: true })
    ).toBeInTheDocument();
  });

  it('shows the reason when the server refuses the pick', async () => {
    vi.mocked(api.getManifestChoices).mockResolvedValue([choice(null)]);
    vi.mocked(api.setManifestChoice).mockResolvedValue({
      message: 'You have no patronage with Hesk.',
      success: false,
    });
    renderWithProviders(<ManifestPickerPanel characterSheetId={SHEET_ID} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Hesk (your patron)' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('You have no patronage with Hesk.');
  });

  it('renders nothing for a character with no technique that brings anyone', async () => {
    vi.mocked(api.getManifestChoices).mockResolvedValue([]);
    renderWithProviders(<ManifestPickerPanel characterSheetId={SHEET_ID} />);
    await vi.waitFor(() => expect(api.getManifestChoices).toHaveBeenCalled());
    expect(screen.queryByTestId('manifest-picker-panel')).not.toBeInTheDocument();
  });
});
