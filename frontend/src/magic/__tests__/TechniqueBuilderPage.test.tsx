import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { MyRosterEntry } from '@/roster/types';
import { TechniqueBuilderPage } from '../pages/TechniqueBuilderPage';

// --- Capture the props the page hands to the (mocked) form ------------------
const formProps = vi.fn();
vi.mock('../components/TechniqueBuilderForm', () => ({
  TechniqueBuilderForm: (props: { characterId?: number }) => {
    formProps(props);
    return <div data-testid="form" data-character-id={props.characterId ?? 'none'} />;
  },
}));

// --- Roster hook is the source of the account's played characters -----------
const useMyRosterEntriesQuery = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => useMyRosterEntriesQuery(),
}));

// --- Stub the lookup-list data sources so the page clears its loading gate --
vi.mock('@/store/hooks', () => ({ useAccount: () => ({ is_staff: false }) }));
vi.mock('@/character-creation/queries', () => ({
  useTechniqueStyles: () => ({ data: [], isLoading: false }),
  useEffectTypes: () => ({ data: [], isLoading: false }),
}));
vi.mock('@/character-creation/api', () => ({ getGifts: () => Promise.resolve([]) }));
vi.mock('@/conditions/queries', () => ({ useDamageTypes: () => ({ data: [], isLoading: false }) }));
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

function entry(character_id: number, name: string): MyRosterEntry {
  return {
    id: character_id,
    name,
    character_id,
    profile_picture_url: null,
    primary_persona_id: null,
    active_persona_id: null,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TechniqueBuilderPage />
    </QueryClientProvider>
  );
}

describe('TechniqueBuilderPage alt wiring (#774)', () => {
  beforeEach(() => {
    formProps.mockClear();
    useMyRosterEntriesQuery.mockReset();
  });

  it('passes the single character id to the form without showing a selector', async () => {
    useMyRosterEntriesQuery.mockReturnValue({ data: [entry(7, 'Solo')] });
    renderPage();

    const form = await screen.findByTestId('form');
    expect(form).toHaveAttribute('data-character-id', '7');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('shows a selector for multi-alt accounts and defaults to the first character', async () => {
    useMyRosterEntriesQuery.mockReturnValue({
      data: [entry(1, 'Alice'), entry(2, 'Bob')],
    });
    renderPage();

    const form = await screen.findByTestId('form');
    expect(form).toHaveAttribute('data-character-id', '1');
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('forwards the picked character id to the form when an alt is selected', async () => {
    const user = userEvent.setup();
    useMyRosterEntriesQuery.mockReturnValue({
      data: [entry(1, 'Alice'), entry(2, 'Bob')],
    });
    renderPage();

    await screen.findByTestId('form');
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Bob' }));

    await waitFor(() =>
      expect(screen.getByTestId('form')).toHaveAttribute('data-character-id', '2')
    );
  });
});
