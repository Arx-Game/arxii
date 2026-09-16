/**
 * Deity Editor pages (#3780): the list's tiles and filters, the edit page's sections and
 * highlight dots, the dashboard's header and tabs.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '../api';
import { BeingDashboardPage } from '../pages/BeingDashboardPage';
import { BeingEditPage } from '../pages/BeingEditPage';
import { PantheonListPage } from '../pages/PantheonListPage';
import type { StaffBeingList, StaffBeingPage } from '../types';

vi.mock('../api');

const tile: StaffBeingList = {
  id: 1,
  name: 'Fleshreaper',
  tradition_name: 'Liturgy',
  nickname: 'the Crimson',
  domain_chips: ['Carnage', 'Bloodshed'],
  resonance_pool: 48200,
  lifetime_worship: 312900,
  visibility: 'public',
  organization_name: '',
  is_active: true,
};

const page: StaffBeingPage = {
  id: 1,
  name: 'Fleshreaper',
  description: 'Goddess of carnage.',
  domains: 'Carnage, bloodshed',
  tradition: 3,
  is_active: true,
  quote: '',
  nicknames: ['the Crimson'],
  resonances: [{ resonance: 5, tier: 'favored' }],
  facets: [],
  feast_days: [],
  tarot_cards: [],
  relationships: [],
  visibility: 'public',
  organization: null,
  gm_notes: '',
  resonance_pool: 48200,
  codex_entry: 9,
};

const options = {
  traditions: [{ id: 3, name: 'Liturgy' }],
  resonances: [{ id: 5, name: 'Savagery' }],
  facets: [],
  tarot_cards: [],
  organizations: [{ id: 7, name: 'The Silken Thread' }],
  beings: [{ id: 1, name: 'Fleshreaper' }],
};

describe('PantheonListPage', () => {
  beforeEach(() => vi.resetAllMocks());

  it('shows a tile per god with the pool beside the name and filters by tier', async () => {
    vi.mocked(api.fetchBeings).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [tile],
    });
    renderWithProviders(<PantheonListPage />);

    const tileEl = await screen.findByTestId('god-tile');
    expect(within(tileEl).getByText('Fleshreaper')).toBeInTheDocument();
    expect(within(tileEl).getByText('48,200')).toBeInTheDocument();
    expect(within(tileEl).getByText('also called the Crimson')).toBeInTheDocument();
    expect(within(tileEl).getByText('Carnage')).toBeInTheDocument();
    expect(screen.getByTestId('add-god')).toHaveAttribute('href', '/staff/pantheon/new');

    await userEvent.click(screen.getByRole('button', { name: 'Obscure' }));
    await waitFor(() =>
      expect(api.fetchBeings).toHaveBeenLastCalledWith({ search: undefined, visibility: 'obscure' })
    );
  });
});

describe('BeingEditPage', () => {
  beforeEach(() => vi.resetAllMocks());

  it('renders every section, dots the unfilled ones, and saves the page', async () => {
    vi.mocked(api.fetchBeingPage).mockResolvedValue(page);
    vi.mocked(api.fetchEditorOptions).mockResolvedValue(options);
    vi.mocked(api.saveBeingPage).mockResolvedValue(page);
    renderWithProviders(
      <Routes>
        <Route path="/staff/pantheon/:id/edit" element={<BeingEditPage />} />
      </Routes>,
      { initialEntries: ['/staff/pantheon/1/edit'] }
    );

    expect(await screen.findByDisplayValue('Fleshreaper')).toBeInTheDocument();
    for (const section of [
      'identity',
      'nicknames',
      'portfolio',
      'feast',
      'tarot',
      'relationships',
      'visibility',
      'notes',
    ]) {
      expect(screen.getByTestId(`section-${section}`)).toBeInTheDocument();
    }
    // Filled: nicknames and portfolio (domains + a resonance). Unfilled: the quote, feast
    // days, tarot, relationships, notes.
    expect(screen.queryByTestId('dot-nicknames')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dot-portfolio')).not.toBeInTheDocument();
    expect(screen.getByTestId('dot-identity')).toBeInTheDocument();
    expect(screen.getByTestId('dot-feast')).toBeInTheDocument();
    expect(screen.getByTestId('dot-notes')).toBeInTheDocument();
    expect(screen.getByTestId('visibility-public')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: '+ Add resonance' })).toHaveAttribute('title');
    // A collapsed section opens on its header and shows its own "+ Add".
    await userEvent.click(screen.getByRole('button', { name: /Nicknames/ }));
    expect(await screen.findByRole('button', { name: '+ Add nickname' })).toHaveAttribute('title');

    await userEvent.click(screen.getByTestId('save-top'));
    await waitFor(() => expect(api.saveBeingPage).toHaveBeenCalledTimes(1));
    const [savedId, saved] = vi.mocked(api.saveBeingPage).mock.calls[0];
    expect(savedId).toBe(1);
    expect(saved.name).toBe('Fleshreaper');
    expect(saved.nicknames).toEqual(['the Crimson']);
    expect(saved.resonances).toEqual([{ resonance: 5, tier: 'favored' }]);
    expect(saved.visibility).toBe('public');
    expect(saved.organization).toBeNull();
  });
});

describe('BeingDashboardPage', () => {
  beforeEach(() => vi.resetAllMocks());

  it('shows the pool and Send Vision in the header and the prayers tab badges', async () => {
    vi.mocked(api.fetchBeingPage).mockResolvedValue(page);
    vi.mocked(api.fetchOverview).mockResolvedValue({
      resonance_pool: 48200,
      lifetime_worship: 312900,
      most_devoted_name: 'Lily',
      most_devoted_favor: 940,
      site_count: 2,
      recent_activity: [
        { when: new Date().toISOString(), text: 'Lily prayed', note: 'act of devotion' },
      ],
    });
    vi.mocked(api.fetchBeingPrayers).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        {
          id: 1,
          character_sheet: 3,
          character_name: 'Marcus',
          text: 'Not like this.',
          devotion_granted: 0,
          dire_straits: 'soulfray',
          answered: true,
          place: '',
          prayed_at: new Date().toISOString(),
        },
        {
          id: 2,
          character_sheet: 4,
          character_name: 'Lily',
          text: 'First blood is yours.',
          devotion_granted: 1,
          dire_straits: '',
          answered: false,
          place: 'The Long Watch',
          prayed_at: new Date().toISOString(),
        },
      ],
    });
    renderWithProviders(
      <Routes>
        <Route path="/staff/pantheon/:id" element={<BeingDashboardPage />} />
      </Routes>,
      { initialEntries: ['/staff/pantheon/1'] }
    );
    expect(await screen.findByTestId('header-pool')).toHaveTextContent('48,200');
    expect(screen.getByTestId('send-vision-button')).toBeInTheDocument();
    expect(await screen.findByTestId('activity-row')).toHaveTextContent('Lily prayed');
    expect(api.fetchBeingPage).toHaveBeenCalledWith(1);

    await userEvent.click(screen.getByRole('tab', { name: 'Prayers' }));
    expect(await screen.findByTestId('prayer-dire')).toHaveTextContent(
      'Dire · soulfray · answered'
    );
    expect(screen.getByTestId('prayer-devotion')).toHaveTextContent('Act of devotion');
    expect(screen.getAllByTestId('prayer-card')).toHaveLength(2);
  });
});
