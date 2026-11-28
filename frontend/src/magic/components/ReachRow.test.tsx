/**
 * ReachRow tests (#5308, #5327): the row offers every resonance with its description, lists the
 * acts she can point at with their suggestions, sends the act she picks, asks for one on a journal
 * entry, and gives way to a warning in an ephemeral scene.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { isReachActMissing, NO_REACH, reachFields, type ReachDraft } from '@/magic/reach';
import type { RecordedAct } from '@/magic/types';
import { ReachRow } from './ReachRow';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getResonanceCatalog: vi.fn(),
  getRecordedActs: vi.fn(),
}));

import * as api from '@/magic/api';

const catalog = [
  {
    id: 31,
    name: 'Cruelty',
    affinity: 1,
    affinity_name: 'Abyssal',
    description: "Pleasure taken from another person's fear or pain.",
    codex_entry_id: null,
    color_hex: '#880000',
  },
  {
    id: 32,
    name: 'Mercy',
    affinity: 2,
    affinity_name: 'Celestial',
    description: '',
    codex_entry_id: null,
    color_hex: '#ffffff',
  },
];

const acts: RecordedAct[] = [
  {
    id: 12,
    label: 'Intimidated Hale',
    created_at: new Date(Date.now() - 2 * 60_000).toISOString(),
    suggestions: [
      {
        resonance_id: 31,
        resonance_name: 'Cruelty',
        reason: 'You left Hale in the grip of Terror.',
      },
    ],
  },
  {
    id: 13,
    label: 'Searched the cellar',
    created_at: new Date(Date.now() - 9 * 60_000).toISOString(),
    suggestions: [],
  },
];

let latest: ReachDraft = NO_REACH;

function Harness(props: { actRequired?: boolean; ephemeral?: boolean }) {
  const [value, setValue] = useState<ReachDraft>(NO_REACH);
  latest = value;
  return <ReachRow characterSheetId={7} value={value} onChange={setValue} {...props} />;
}

async function chooseCruelty(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByTestId('reach-toggle'));
  await user.selectOptions(screen.getByTestId('reach-select'), '31');
}

describe('ReachRow', () => {
  beforeEach(() => {
    latest = NO_REACH;
    vi.mocked(api.getResonanceCatalog).mockReset().mockResolvedValue(catalog);
    vi.mocked(api.getRecordedActs).mockReset().mockResolvedValue(acts);
  });

  it("shows the chosen resonance's description and no help for one with none", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await chooseCruelty(user);

    expect(screen.getByTestId('reach-help')).toHaveTextContent(
      "Pleasure taken from another person's fear or pain."
    );
    await user.selectOptions(screen.getByTestId('reach-select'), '32');
    expect(screen.queryByTestId('reach-help')).toBeNull();
  });

  it('lists her acts with age and suggestion, and "Nothing" is chosen to begin with', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await chooseCruelty(user);

    expect(await screen.findByText('Intimidated Hale')).toBeInTheDocument();
    expect(screen.getByText('2 minutes ago')).toBeInTheDocument();
    expect(
      screen.getByText('Suggested: Cruelty. You left Hale in the grip of Terror.')
    ).toBeInTheDocument();
    expect(screen.getByText('No resonance suggested.')).toBeInTheDocument();
    expect(screen.getByText('Pointing at')).toBeInTheDocument();
    expect(screen.getByTestId('reach-act-none')).toBeChecked();
    expect(reachFields(latest)).toEqual({ reach_resonance_id: 31 });
  });

  it('names the strongest suggestion when none is for the resonance she chose', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await user.click(await screen.findByTestId('reach-toggle'));
    await user.selectOptions(screen.getByTestId('reach-select'), '32');

    expect(
      await screen.findByText('Suggested: Cruelty. You left Hale in the grip of Terror.')
    ).toBeInTheDocument();
  });

  it('sends the act she points at beside the resonance, and "Nothing" takes it back', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await chooseCruelty(user);

    await user.click(await screen.findByTestId('reach-act-12'));
    expect(reachFields(latest)).toEqual({ reach_resonance_id: 31, reach_act_id: 12 });

    await user.click(screen.getByTestId('reach-act-none'));
    expect(reachFields(latest)).toEqual({ reach_resonance_id: 31 });
  });

  it('asks for an act on a journal entry and offers no "Nothing" choice', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness actRequired />);
    await chooseCruelty(user);

    expect(await screen.findByText('Pointing at (required)')).toBeInTheDocument();
    expect(screen.queryByTestId('reach-act-none')).toBeNull();
    expect(isReachActMissing(latest)).toBe(true);

    await user.click(screen.getByTestId('reach-act-12'));
    expect(isReachActMissing(latest)).toBe(false);
  });

  it('says there is nothing to point at when a journal entry has no acts', async () => {
    vi.mocked(api.getRecordedActs).mockResolvedValue([]);
    const user = userEvent.setup();
    renderWithProviders(<Harness actRequired />);
    await chooseCruelty(user);

    expect(await screen.findByTestId('reach-no-acts')).toBeInTheDocument();
  });

  it('shows a warning in an ephemeral scene instead of the act list, and reads no acts', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness ephemeral />);
    await chooseCruelty(user);

    expect(screen.getByTestId('reach-ephemeral')).toHaveTextContent(
      'This scene is ephemeral and stores nothing, so a mark here pays nothing. Mark the act later, in a pose in another scene or from a journal entry.'
    );
    expect(screen.queryByTestId('reach-acts')).toBeNull();
    expect(api.getRecordedActs).not.toHaveBeenCalled();
  });

  it('reads no acts until a resonance is chosen, and closing the row forgets the pick', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await user.click(await screen.findByTestId('reach-toggle'));
    expect(api.getRecordedActs).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByTestId('reach-select'), '31');
    await user.click(await screen.findByTestId('reach-act-12'));
    await user.click(screen.getByTestId('reach-toggle'));
    expect(latest).toEqual(NO_REACH);
    expect(reachFields(latest)).toEqual({});
  });
});
