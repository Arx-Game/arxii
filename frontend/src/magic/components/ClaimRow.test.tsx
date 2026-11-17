/**
 * ClaimRow tests (#5181): the row appears only while something is waiting, starts with
 * everything waiting ticked, sends an empty id list for all of it and only the ticked ids for
 * a subset.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { claimFields, NO_CLAIM, waitingClaims, type ClaimDraft } from '@/magic/claiming';
import type { KindledResonance } from '@/magic/types';
import { ClaimRow } from './ClaimRow';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getKindledResonances: vi.fn(),
}));

import * as api from '@/magic/api';

const ruin: KindledResonance = {
  id: 1,
  name: 'Ruin',
  affinity_name: 'Abyssal',
  kindled: true,
  strength_name: 'Blazing',
  reasons: [],
  unclaimed: 5,
  claim_verb: 'gloat',
};
const mercy: KindledResonance = {
  id: 2,
  name: 'Mercy',
  affinity_name: 'Celestial',
  kindled: false,
  strength_name: null,
  reasons: [],
  unclaimed: 3,
  claim_verb: 'inspire',
};
const quiet: KindledResonance = { ...ruin, id: 3, name: 'Wonder', unclaimed: 0 };

let latest: ClaimDraft = NO_CLAIM;

function Harness() {
  const [value, setValue] = useState<ClaimDraft>(NO_CLAIM);
  latest = value;
  return <ClaimRow characterSheetId={7} value={value} onChange={setValue} />;
}

describe('ClaimRow', () => {
  beforeEach(() => {
    latest = NO_CLAIM;
    vi.mocked(api.getKindledResonances).mockReset();
  });

  it('starts with everything waiting ticked and sends an empty list for all of it', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({
      results: [ruin, mercy, quiet],
      impulses: [],
    });
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(await screen.findByTestId('claim-toggle'));

    expect(screen.getByTestId('claim-resonance-1')).toBeChecked();
    expect(screen.getByTestId('claim-resonance-2')).toBeChecked();
    expect(screen.queryByTestId('claim-resonance-3')).not.toBeInTheDocument();
    expect(screen.getByText('5 Ruin')).toBeInTheDocument();
    expect(screen.getByText('3 Mercy')).toBeInTheDocument();
    expect(claimFields(latest, waitingClaims([ruin, mercy, quiet]))).toEqual({
      claim: true,
      claim_resonance_ids: [],
    });
  });

  it('sends only the ticked ids once some are unticked', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: [ruin, mercy], impulses: [] });
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(await screen.findByTestId('claim-toggle'));
    await user.click(screen.getByTestId('claim-resonance-2'));

    expect(claimFields(latest, [ruin, mercy])).toEqual({ claim: true, claim_resonance_ids: [1] });
  });

  it('sends nothing while the switch is off, and renders nothing when nothing waits', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: [quiet], impulses: [] });
    renderWithProviders(<Harness />);

    await vi.waitFor(() => expect(api.getKindledResonances).toHaveBeenCalled());
    expect(screen.queryByTestId('claim-row')).not.toBeInTheDocument();
    expect(claimFields(latest, [ruin])).toEqual({});
  });
});
