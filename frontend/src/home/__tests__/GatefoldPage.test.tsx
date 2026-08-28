/**
 * GatefoldPage component tests (#3305).
 *
 * All data hooks are mocked — this exercises composition/wiring (chapters
 * render what their hooks return, the excerpt block disappears on a null
 * resolution, the Door reacts to registration status and auth state), not
 * the network layer.
 */

import { cleanup, screen } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { GatefoldPage } from '../GatefoldPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import type { StartingArea } from '@/character-creation/types';
import type { CodexEntryListItem } from '@/codex/types';

// #3412 slice 2 — GatefoldPage now mounts HallPage (instead of the gatefold
// chapters) for an authenticated account. HallPage's own content is covered
// by its own test suite; this file only needs to assert the mount split, so
// HallPage is stubbed to a marker.
vi.mock('../HallPage', () => ({
  HallPage: () => <div data-testid="hall-page-stub" />,
}));

const mockUsePublicStartingAreas = vi.fn();
const mockUsePublicBeginnings = vi.fn();
const mockUseSceneExcerpt = vi.fn();
const mockUseMonthlySceneCount = vi.fn();
const mockUseFeaturedLore = vi.fn();
vi.mock('../queries', () => ({
  usePublicStartingAreas: () => mockUsePublicStartingAreas(),
  usePublicBeginnings: (...args: unknown[]) => mockUsePublicBeginnings(...args),
  useSceneExcerpt: () => mockUseSceneExcerpt(),
  useMonthlySceneCount: () => mockUseMonthlySceneCount(),
  useFeaturedLore: () => mockUseFeaturedLore(),
}));

const mockUseRegistrationStatus = vi.fn();
vi.mock('@/evennia_replacements/queries', () => ({
  useRegistrationStatus: () => mockUseRegistrationStatus(),
}));

const mockUsePageBackgrounds = vi.fn();
vi.mock('@/hooks/usePageBackgrounds', () => ({
  usePageBackgrounds: () => mockUsePageBackgrounds(),
  pageBackgroundStyle: () => ({}),
}));

const mockSetForcedRealm = vi.fn();
vi.mock('@/components/realm-theme-provider', () => ({
  useRealmTheme: () => ({ setForcedRealm: mockSetForcedRealm }),
}));

const mockUseDraft = vi.fn();
vi.mock('@/character-creation/queries', () => ({
  useDraft: (...args: unknown[]) => mockUseDraft(...args),
}));

const startingAreas: StartingArea[] = [
  {
    id: 1,
    name: 'The Ward of the Compact',
    description: 'Where the living still keep their lamps lit.',
    crest_image: null,
    is_accessible: true,
    realm_theme: 'arx',
  },
  {
    id: 2,
    name: 'The Undercroft',
    description: 'Shadows and ledgers, in equal measure.',
    crest_image: null,
    is_accessible: true,
    realm_theme: 'umbros',
  },
];

const codexEntries: CodexEntryListItem[] = [
  {
    id: 10,
    name: 'The Shroud',
    summary: 'A grey veil no army and no messenger ever crossed.',
    is_public: true,
    is_featured: true,
    featured_order: 1,
    subject: 1,
    subject_name: 'The World',
    subject_path: [],
    display_order: 1,
    knowledge_status: null,
    known_by: [],
    art_url: null,
    perspective_of: null,
  },
];

function setDefaultMocks() {
  mockUsePublicStartingAreas.mockReturnValue({ data: startingAreas, isLoading: false });
  mockUsePublicBeginnings.mockReturnValue({ data: [], isLoading: false });
  mockUseSceneExcerpt.mockReturnValue({ data: null });
  mockUseMonthlySceneCount.mockReturnValue({ data: undefined });
  mockUseFeaturedLore.mockReturnValue({ data: codexEntries, isLoading: false });
  mockUseRegistrationStatus.mockReturnValue({ data: { open: true } });
  mockUsePageBackgrounds.mockReturnValue({ data: [] });
  mockUseDraft.mockReturnValue({ data: null });
}

describe('GatefoldPage', () => {
  afterEach(() => {
    // Unmount BEFORE mutating the store (#3412 fix): GatefoldPage's
    // forced-realm effect now depends on `account`, so a store mutation
    // while the previous test's tree is still mounted (RTL's own cleanup
    // hasn't fired yet) re-renders it and fires an un-`act()`-wrapped effect
    // that leaks a stray `setForcedRealm` call into the NEXT test's mock
    // call log. Explicit `cleanup()` first removes that live tree before
    // the store mutation has anything left to re-render.
    cleanup();
    store.dispatch(setAccount(null));
    vi.clearAllMocks();
  });

  it('forces the arx realm theme on mount', () => {
    setDefaultMocks();
    renderWithProviders(<GatefoldPage />);

    expect(mockSetForcedRealm).toHaveBeenCalledWith('arx');
  });

  it('renders realm rows and codex entries', () => {
    setDefaultMocks();
    renderWithProviders(<GatefoldPage />);

    expect(screen.getByText('The Ward of the Compact')).toBeInTheDocument();
    expect(screen.getByText('The Undercroft')).toBeInTheDocument();
    expect(screen.getByText('The Shroud')).toBeInTheDocument();
  });

  it('omits the scene excerpt block when useSceneExcerpt resolves null', () => {
    setDefaultMocks();
    renderWithProviders(<GatefoldPage />);

    expect(screen.queryByText(/A public scene/)).not.toBeInTheDocument();
  });

  it('renders the scene excerpt when useSceneExcerpt resolves data', () => {
    setDefaultMocks();
    mockUseSceneExcerpt.mockReturnValue({
      data: {
        scene: {
          id: 5,
          name: "The Lamplighter's Rounds",
          description: '',
          date_started: '2026-08-01T00:00:00Z',
          location: { id: 1, name: 'the Ward of the Compact' },
          participants: [
            { id: 1, name: 'Serane' },
            { id: 2, name: 'A stranger' },
          ],
        },
        poses: [{ id: 100, content: 'Serane sets her taper to the fourth lamp on the row.' }],
      },
    });
    renderWithProviders(<GatefoldPage />);

    expect(screen.getByText("The Lamplighter's Rounds")).toBeInTheDocument();
    expect(
      screen.getByText('Serane sets her taper to the fourth lamp on the row.')
    ).toBeInTheDocument();
    expect(screen.getByText(/A public scene in the Ward of the Compact/)).toBeInTheDocument();
  });

  it('shows the Begin CTA when registration is open and the visitor is a guest', () => {
    setDefaultMocks();
    renderWithProviders(<GatefoldPage />);

    expect(screen.getByRole('link', { name: 'Begin' })).toHaveAttribute('href', '/register');
  });

  it('shows the invite-only notice when registration is closed', () => {
    setDefaultMocks();
    mockUseRegistrationStatus.mockReturnValue({ data: { open: false } });
    renderWithProviders(<GatefoldPage />);

    expect(screen.queryByRole('link', { name: 'Begin' })).not.toBeInTheDocument();
    expect(screen.getByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Read how it works' })).toHaveAttribute(
      'href',
      '/how-to-start'
    );
  });

  it('renders HallPage instead of the gatefold chapters for an authenticated account (#3412)', () => {
    setDefaultMocks();
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<GatefoldPage />);

    expect(screen.getByTestId('hall-page-stub')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Begin' })).not.toBeInTheDocument();
    expect(screen.queryByText('The Ward of the Compact')).not.toBeInTheDocument();
    expect(screen.queryByText(/How One Enters/)).not.toBeInTheDocument();
  });

  it('does not force the arx realm theme for an authenticated account (#3412 — Hall uses its own realm)', () => {
    setDefaultMocks();
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<GatefoldPage />);

    expect(mockSetForcedRealm).not.toHaveBeenCalledWith('arx');
  });

  it('renders the gatefold chapters unchanged for a visitor (byte-identical mount split)', () => {
    setDefaultMocks();
    renderWithProviders(<GatefoldPage />);

    expect(screen.queryByTestId('hall-page-stub')).not.toBeInTheDocument();
    expect(screen.getByText('The Ward of the Compact')).toBeInTheDocument();
  });

  it('does not blank the page when the featured-entries query errors', () => {
    setDefaultMocks();
    // No throwOnError anywhere on this page (fix round 1, finding 1) — an
    // errored query resolves with `data: undefined`, never an uncaught throw.
    mockUseFeaturedLore.mockReturnValue({ data: undefined, isLoading: false });
    const { container } = renderWithProviders(<GatefoldPage />);

    expect(container).not.toBeEmptyDOMElement();
    // The chapter's own prose still renders — only the index list is hidden.
    expect(screen.getByText('Of the Empty City')).toBeInTheDocument();
    expect(screen.queryByText('The Shroud')).not.toBeInTheDocument();
  });

  it('does not blank the page when the featured-entries query returns nothing', () => {
    setDefaultMocks();
    mockUseFeaturedLore.mockReturnValue({ data: [], isLoading: false });
    const { container } = renderWithProviders(<GatefoldPage />);

    expect(container).not.toBeEmptyDOMElement();
    expect(screen.getByText('Of the Empty City')).toBeInTheDocument();
  });

  it('shows the monthly scene count line when the count is positive', () => {
    setDefaultMocks();
    mockUseMonthlySceneCount.mockReturnValue({ data: 14 });
    renderWithProviders(<GatefoldPage />);

    expect(screen.getByText(/14 public scenes concluded this month/)).toBeInTheDocument();
  });

  it('hides the monthly scene count line when the count is 0', () => {
    setDefaultMocks();
    mockUseMonthlySceneCount.mockReturnValue({ data: 0 });
    renderWithProviders(<GatefoldPage />);

    expect(screen.queryByText(/concluded this month/)).not.toBeInTheDocument();
  });

  it('hides the monthly scene count line when the count is undefined', () => {
    setDefaultMocks();
    mockUseMonthlySceneCount.mockReturnValue({ data: undefined });
    renderWithProviders(<GatefoldPage />);

    expect(screen.queryByText(/concluded this month/)).not.toBeInTheDocument();
  });
});
