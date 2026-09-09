import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RealmPage } from '../pages/RealmPage';
import type { RealmDetail } from '../types';

const setForcedRealm = vi.fn();
vi.mock('@/components/realm-theme-provider', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/realm-theme-provider')>();
  return { ...actual, useRealmTheme: () => ({ setForcedRealm }) };
});

const realm: RealmDetail = {
  id: 1,
  name: 'Umbros',
  slug: 'umbros',
  formal_name: 'The Umbral Empire',
  theme: 'umbros',
  first_motto: 'Dare Greatly.',
  threshold_line: 'One stands before us in Durance. Speak thy name and testament.',
  sections: [
    { sort_order: 1, body: 'First paragraph.\n\nSecond paragraph.', motto: 'Dare Greatly.' },
    { sort_order: 2, body: 'Third paragraph.', motto: 'Return puissant.' },
  ],
  societies: [
    { id: 5, name: 'The Peerage', description: 'What it says.', enforcer_name: 'The Tannistry' },
  ],
  starting_area: { id: 6, name: 'Tenebrum', crest_image: null },
};

const mocks = vi.hoisted(() => ({
  realm: { data: undefined as unknown, isLoading: false, isError: false },
  orgs: { data: undefined as unknown },
  boards: { data: undefined as unknown },
  roster: { data: undefined as unknown },
}));

vi.mock('../queries', () => ({
  useRealm: () => mocks.realm,
  useRealmOrganizations: () => mocks.orgs,
  useRealmNotables: () => mocks.boards,
  useRealmRoster: () => mocks.roster,
}));

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/realms/:slug" element={<RealmPage />} />
    </Routes>,
    { initialEntries: ['/realms/umbros'] }
  );
}

describe('RealmPage (#3725)', () => {
  beforeEach(() => {
    setForcedRealm.mockClear();
    mocks.realm = { data: realm, isLoading: false, isError: false };
    mocks.orgs = { data: undefined };
    mocks.boards = { data: undefined };
    mocks.roster = { data: undefined };
  });

  it('renders the testament in movements with their mottos and forces the realm palette', () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Umbros' })).toBeInTheDocument();
    expect(screen.getByText('The Umbral Empire')).toBeInTheDocument();
    expect(screen.getByText(/Speak thy name and testament/)).toBeInTheDocument();
    expect(screen.getByText('First paragraph.')).toBeInTheDocument();
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument();
    expect(screen.getByText('Dare Greatly.')).toBeInTheDocument();
    expect(screen.getByText('Return puissant.')).toBeInTheDocument();
    expect(setForcedRealm).toHaveBeenCalledWith('umbros');
    expect(screen.getByText(/Tenebrum is the way into Umbros/)).toBeInTheDocument();
  });

  it('has the rail above the testament and every hub section with its empty state', () => {
    renderPage();
    const rail = screen.getByRole('navigation', { name: /sections of this realm/i });
    expect(
      within(rail)
        .getAllByRole('link')
        .map((a) => a.getAttribute('href'))
    ).toEqual(['#testament', '#societies', '#houses', '#names', '#characters']);
    expect(screen.getByText('The Peerage')).toBeInTheDocument();
    expect(screen.getByText(/its enforcer: The Tannistry/)).toBeInTheDocument();
    expect(
      screen.getByText(/No houses or organizations are recorded here yet/)
    ).toBeInTheDocument();
    expect(screen.getAllByText('No names are spoken here yet.')).toHaveLength(2);
    expect(screen.getByText(/No characters of Umbros are on the roster yet/)).toBeInTheDocument();
  });

  it('lists organizations by kind as links and boards as names with a phrase, never a number', () => {
    mocks.orgs = {
      data: [
        {
          id: 9,
          name: 'House Veyle',
          description: '',
          words: 'Dare, and be remembered.',
          colors: '',
          sigil_description: 'a black stag',
          org_type_name: 'noble',
          society_name: 'The Peerage',
        },
      ],
    };
    mocks.boards = {
      data: {
        renown: [{ persona_name: 'Isolde Veyle', band_label: 'First among the peers' }],
        legend: [],
      },
    };
    renderPage();
    expect(screen.getByRole('link', { name: 'House Veyle' })).toHaveAttribute('href', '/orgs/9');
    expect(screen.getByText(/Dare, and be remembered/)).toBeInTheDocument();
    expect(screen.getByText('Isolde Veyle')).toBeInTheDocument();
    expect(screen.getByText('First among the peers')).toBeInTheDocument();
    expect(screen.getAllByText('No names are spoken here yet.')).toHaveLength(1);
  });

  it('shows the characters of the realm and hands off to the roster filtered by realm', () => {
    mocks.roster = {
      data: {
        count: 14,
        next: null,
        previous: null,
        results: [
          {
            id: 3,
            character: { id: 3, name: 'Isolde Veyle', char_class: 'Duelist' },
            profile_picture: null,
          },
        ],
      },
    };
    renderPage();
    expect(screen.getAllByText('Isolde Veyle').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /All 14 characters of Umbros/ })).toHaveAttribute(
      'href',
      '/roster?realm=umbros'
    );
  });

  it('tells a visitor when there is no realm by that name', () => {
    mocks.realm = { data: undefined, isLoading: false, isError: true };
    renderPage();
    expect(screen.getByText('No realm by that name.')).toBeInTheDocument();
  });
});
