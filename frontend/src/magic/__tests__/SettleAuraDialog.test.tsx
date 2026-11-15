/**
 * Coverage for the rite of settling dialog (#5124, Screen 6 of the approved demo): real
 * hooks (useSettlingRite / usePerformSettlingRite) over a mocked api transport, the same
 * pattern as EntryFlourishOfferDialog.test.tsx.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { SettleAuraDialog } from '../components/SettleAuraDialog';
import { offeringLabel } from '../riteText';
import type { RiteOffering, RiteReflection, SettlingRiteReading } from '../types';

vi.mock('../api', () => ({
  getSettlingRite: vi.fn(),
  performSettlingRite: vi.fn(),
}));

import * as api from '../api';

const JOURNAL_REFLECTION: RiteReflection = {
  id: 1,
  choice: 'DISOWN',
  kind: 'resonance',
  title: 'Disown your Domination',
  where: '"The collar" · journal',
  from_line: 'from your journal, "The collar"',
  excerpt: 'I set the iron collar on the altar and made myself look at it.',
  effect_line: 'Domination turns toward Fury, up to 3.',
};
const POSE_REFLECTION: RiteReflection = {
  id: 2,
  choice: 'EMBRACE',
  kind: 'deed',
  title: "Embrace Barred the overseers' door",
  where: 'Pose in The Quarry',
  from_line: 'from your pose in The Quarry',
  excerpt: 'They had it coming. All of them.',
  effect_line: 'Your Domination from the door grows, up to 5.',
};
const COLLAR: RiteOffering = {
  item_id: 501,
  name: 'Iron collar',
  mode: 'keepsake',
  resonance_name: 'Fury',
  focus_bonus: 2,
};
const THREAD: RiteOffering = {
  item_id: 502,
  name: 'Dawn-gold Thread',
  mode: 'material',
  resonance_name: 'Dawnlight',
  focus_bonus: 0,
};

function reading(overrides: Partial<SettlingRiteReading> = {}): SettlingRiteReading {
  return {
    reflections: [JOURNAL_REFLECTION, POSE_REFLECTION],
    offerings: [COLLAR],
    rite_ready: true,
    not_ready_message: '',
    check_name: 'Composure',
    ...overrides,
  };
}

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<SettleAuraDialog characterSheetId={55} open onOpenChange={onOpenChange} />, { wrapper });
  return onOpenChange;
}

describe('SettleAuraDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists every waiting reflection with its writing and what the rite will do', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading());
    renderDialog();

    expect(await screen.findByText('Settling your aura')).toBeInTheDocument();
    expect(api.getSettlingRite).toHaveBeenCalledWith(55);
    const journal = await screen.findByTestId('rite-reflection-1');
    expect(journal).toHaveTextContent('Disown your Domination');
    expect(journal).toHaveTextContent(
      '“I set the iron collar on the altar and made myself look at it.” from your journal, "The collar"'
    );
    expect(journal).toHaveTextContent('Domination turns toward Fury, up to 3.');
    expect(screen.getByTestId('rite-reflection-2')).toHaveTextContent(
      'from your pose in The Quarry'
    );
  });

  it('takes a lone offering as the choice and says what is rolled, with the focus bonus', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading());
    renderDialog();

    const offering = await screen.findByTestId('rite-offering-501');
    expect(offering).toHaveTextContent('Iron collar · a keepsake of Fury');
    expect(offering).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('rite-roll')).toHaveTextContent(
      'Roll: Composure, +2 from your worn focus. A full success carries out every reflection in full'
    );
    expect(screen.getByTestId('rite-roll')).toHaveTextContent(
      'The offering is spent whatever the roll.'
    );
    expect(screen.getByTestId('rite-perform')).toBeEnabled();
  });

  it('asks the player to pick among several offerings and sends exactly that item', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading({ offerings: [COLLAR, THREAD] }));
    vi.mocked(api.performSettlingRite).mockResolvedValue({
      outcome_name: 'Success',
      success_level: 1,
      focus_bonus: 0,
      lines: ['You disown your Domination: 3 Domination became 1 Fury.'],
    });
    renderDialog();

    await screen.findByTestId('rite-offering-502');
    expect(screen.getByTestId('rite-perform')).toBeDisabled();
    await user.click(screen.getByTestId('rite-offering-502'));
    // No focus line for an offering with no bonus.
    expect(screen.getByTestId('rite-roll')).not.toHaveTextContent('worn focus');
    await user.click(screen.getByTestId('rite-perform'));

    await waitFor(() =>
      expect(api.performSettlingRite).toHaveBeenCalledWith({
        character_sheet_id: 55,
        component_ids: [502],
      })
    );
    const result = await screen.findByTestId('rite-result');
    expect(result).toHaveTextContent('Success.');
    expect(result).toHaveTextContent('You disown your Domination: 3 Domination became 1 Fury.');
    expect(screen.queryByTestId('rite-perform')).not.toBeInTheDocument();
  });

  it('shows the server sentence when the rite refuses, and keeps the reflections', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading());
    vi.mocked(api.performSettlingRite).mockRejectedValue(
      new Error('You are not carrying everything you offered.')
    );
    renderDialog();

    await user.click(await screen.findByTestId('rite-perform'));

    expect(await screen.findByTestId('rite-error')).toHaveTextContent(
      'You are not carrying everything you offered.'
    );
    expect(screen.getByTestId('rite-reflection-1')).toBeInTheDocument();
  });

  it('says so when nothing carried counts as the offering', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading({ offerings: [] }));
    renderDialog();

    expect(await screen.findByTestId('rite-no-offering')).toHaveTextContent(
      'You carry nothing that counts as the offering.'
    );
    expect(screen.getByTestId('rite-perform')).toBeDisabled();
  });

  it('shows the not-ready sentence in place of the offering and never enables the rite', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(
      reading({
        rite_ready: false,
        not_ready_message: 'The rite of settling is not set up yet; tell staff.',
        offerings: [],
      })
    );
    renderDialog();

    expect(await screen.findByTestId('rite-not-ready')).toHaveTextContent(
      'The rite of settling is not set up yet; tell staff.'
    );
    expect(screen.queryByTestId('rite-roll')).not.toBeInTheDocument();
    expect(screen.getByTestId('rite-perform')).toBeDisabled();
  });

  it('Not now closes without performing anything', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading());
    const onOpenChange = renderDialog();

    await user.click(await screen.findByTestId('settle-not-now'));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.performSettlingRite).not.toHaveBeenCalled();
  });

  it('carries the sheet rust class the portal would otherwise miss', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(reading());
    renderDialog();

    expect(await screen.findByRole('dialog')).toHaveClass('aura-settle-dialog');
  });

  it('names how an offering counts: tied, a facet, or a keepsake', () => {
    expect(offeringLabel(THREAD)).toBe('Dawn-gold Thread · tied to Dawnlight');
    expect(offeringLabel({ ...THREAD, mode: 'facet' })).toBe(
      'Dawn-gold Thread · bears a facet of Dawnlight'
    );
    expect(offeringLabel(COLLAR)).toBe('Iron collar · a keepsake of Fury');
  });
});
