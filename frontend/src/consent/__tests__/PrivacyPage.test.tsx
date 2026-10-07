import { vi } from 'vitest';

// ---------------------------------------------------------------------------
// Mock Radix Select to avoid jsdom portal/pointer-event issues in tests
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
    disabled,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
    disabled?: boolean;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

// ---------------------------------------------------------------------------
// Mock all consent hooks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useConsentCategories: vi.fn(),
  useConsentModes: vi.fn(),
  useConsentPreference: vi.fn(),
  useCreatePreference: vi.fn(),
  useUpdatePreference: vi.fn(),
  useCategoryRules: vi.fn(),
  useUpsertCategoryRule: vi.fn(),
  useDeleteCategoryRule: vi.fn(),
  useWhitelist: vi.fn(),
  useAddWhitelist: vi.fn(),
  useRemoveWhitelist: vi.fn(),
  useBlacklist: vi.fn(),
  useAddBlacklist: vi.fn(),
  useRemoveBlacklist: vi.fn(),
}));

// Mock MyTenureSelect so we can control character selection
vi.mock('@/components/MyTenureSelect', () => ({
  default: ({
    value,
    onChange,
    label,
  }: {
    value: number | null;
    onChange: (v: number | null) => void;
    label?: string;
  }) => (
    <div>
      <label htmlFor="my-tenure-select">{label ?? 'Character'}</label>
      <select
        id="my-tenure-select"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Select tenure</option>
        <option value="1">Aria</option>
        <option value="2">Bram</option>
      </select>
    </div>
  ),
}));

// Mock ErrorBoundary to be a passthrough in tests
vi.mock('@/components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock useTenureSearch for whitelist add picker
vi.mock('@/mail/queries', () => ({
  useTenureSearch: vi.fn(),
  useMailQuery: vi.fn(),
  useSendMail: vi.fn(),
}));

import React from 'react';
import { screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PrivacyPage } from '../pages/PrivacyPage';
import * as queries from '../queries';
import * as mailQueries from '@/mail/queries';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockCategories = [
  {
    id: 10,
    key: 'romantic',
    name: 'Romantic',
    description: 'Romantic interactions.',
    display_order: 1,
    parent: null,
    default_mode: 'everyone',
    asks_before_acting: false,
    action_templates: [],
  },
  {
    id: 20,
    key: 'hostile',
    name: 'Hostile',
    description: 'Hostile interactions.',
    display_order: 2,
    parent: null,
    default_mode: 'everyone',
    asks_before_acting: false,
    action_templates: [],
  },
  {
    id: 30,
    key: 'makeover',
    name: 'Makeovers & Styling',
    description: 'Other characters restyling your appearance.',
    display_order: 3,
    parent: null,
    default_mode: 'ask',
    asks_before_acting: true,
    action_templates: [],
  },
];

const mockModes = [
  { value: 'everyone', label: 'Everyone', guidance: 'Anyone may do this to you.' },
  { value: 'friends_whitelist', label: 'Friends + whitelist', guidance: 'Only friends.' },
  { value: 'rivals', label: 'My declared rivals', guidance: 'Only mutual rivals.' },
  { value: 'allowlist', label: 'Allowlist only', guidance: 'Only people you allow.' },
  {
    value: 'all_but_blacklist',
    label: 'Everyone except blacklist',
    guidance: 'Anyone but your blacklist.',
  },
];

const mockPreferenceWithId = { id: 5, tenure: 1, allow_social_actions: true };
const mockPreferenceNoId = {
  id: undefined as unknown as number,
  tenure: 1,
  allow_social_actions: true,
};

function setupDefaultMocks() {
  const upsertMutate = vi.fn();
  const deleteMutate = vi.fn();
  const addMutate = vi.fn();
  const removeMutate = vi.fn();
  const updateMutate = vi.fn();
  const createMutateAsync = vi.fn();

  vi.mocked(queries.useConsentCategories).mockReturnValue({
    data: { count: 3, results: mockCategories },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useConsentCategories>);

  vi.mocked(queries.useConsentModes).mockReturnValue({
    data: mockModes,
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useConsentModes>);

  vi.mocked(queries.useConsentPreference).mockReturnValue({
    data: mockPreferenceWithId,
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useConsentPreference>);

  vi.mocked(queries.useCreatePreference).mockReturnValue({
    mutateAsync: createMutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useCreatePreference>);

  vi.mocked(queries.useUpdatePreference).mockReturnValue({
    mutate: updateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useUpdatePreference>);

  vi.mocked(queries.useCategoryRules).mockReturnValue({
    data: { count: 0, results: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useCategoryRules>);

  vi.mocked(queries.useUpsertCategoryRule).mockReturnValue({
    mutate: upsertMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useUpsertCategoryRule>);

  vi.mocked(queries.useDeleteCategoryRule).mockReturnValue({
    mutate: deleteMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useDeleteCategoryRule>);

  vi.mocked(queries.useWhitelist).mockReturnValue({
    data: { count: 0, results: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useWhitelist>);

  vi.mocked(queries.useAddWhitelist).mockReturnValue({
    mutate: addMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useAddWhitelist>);

  vi.mocked(queries.useRemoveWhitelist).mockReturnValue({
    mutate: removeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useRemoveWhitelist>);

  const addBlacklistMutate = vi.fn();
  const removeBlacklistMutate = vi.fn();

  vi.mocked(queries.useBlacklist).mockReturnValue({
    data: { count: 0, results: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useBlacklist>);

  vi.mocked(queries.useAddBlacklist).mockReturnValue({
    mutate: addBlacklistMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useAddBlacklist>);

  vi.mocked(queries.useRemoveBlacklist).mockReturnValue({
    mutate: removeBlacklistMutate,
    isPending: false,
  } as unknown as ReturnType<typeof queries.useRemoveBlacklist>);

  vi.mocked(mailQueries.useTenureSearch).mockReturnValue({
    data: { count: 0, results: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof mailQueries.useTenureSearch>);

  return {
    upsertMutate,
    deleteMutate,
    addMutate,
    removeMutate,
    updateMutate,
    createMutateAsync,
    addBlacklistMutate,
    removeBlacklistMutate,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/** The Romantic row (category 10): the asking Makeovers row renders both list managers too. */
function romanticRow() {
  const row = screen.getByText('Romantic').closest('[data-testid="category-row"]');
  if (!row) throw new Error('Romantic row not rendered');
  return within(row as HTMLElement);
}

describe('PrivacyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Initial state — no character selected
  // -------------------------------------------------------------------------

  it('renders character selector before a character is chosen', () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);
    expect(screen.getByLabelText('Character')).toBeInTheDocument();
    // No consent panel rendered yet
    expect(screen.queryByText('Social targeting')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Renders categories once a character is selected
  // -------------------------------------------------------------------------

  it('renders consent categories after selecting a character', async () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => {
      expect(screen.getByText('Romantic')).toBeInTheDocument();
      expect(screen.getByText('Hostile')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // WhitelistManager revealed when mode = "allowlist"
  // -------------------------------------------------------------------------

  it('calls upsertCategoryRule when switching to allowlist mode', async () => {
    const { upsertMutate } = setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => screen.getByText('Romantic'));

    // Each category has a mocked <select>. The first one corresponds to "Romantic".
    const selects = screen.getAllByTestId('mock-select');
    // Change first select (Romantic row) to "allowlist"
    fireEvent.change(selects[0], { target: { value: 'allowlist' } });

    expect(upsertMutate).toHaveBeenCalledWith({
      preference: mockPreferenceWithId.id,
      category: mockCategories[0].id,
      mode: 'allowlist',
    });
  });

  // -------------------------------------------------------------------------
  // #1698 — new modes upsert with their value
  // -------------------------------------------------------------------------

  it('calls upsertCategoryRule when switching to all_but_blacklist mode', async () => {
    const { upsertMutate } = setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });
    await waitFor(() => screen.getByText('Romantic'));

    const selects = screen.getAllByTestId('mock-select');
    fireEvent.change(selects[0], { target: { value: 'all_but_blacklist' } });

    expect(upsertMutate).toHaveBeenCalledWith({
      preference: mockPreferenceWithId.id,
      category: mockCategories[0].id,
      mode: 'all_but_blacklist',
    });
  });

  it('deletes the rule (reverts to inherited) when choosing Inherit (#2170)', async () => {
    const { deleteMutate } = setupDefaultMocks();
    // Romantic has an explicit allowlist rule; choosing "inherit" should delete it.
    vi.mocked(queries.useCategoryRules).mockReturnValue({
      data: { count: 1, results: [{ id: 42, preference: 5, category: 10, mode: 'allowlist' }] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useCategoryRules>);

    renderWithProviders(<PrivacyPage />);
    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });
    await waitFor(() => screen.getByText('Romantic'));

    const selects = screen.getAllByTestId('mock-select');
    fireEvent.change(selects[0], { target: { value: 'inherit' } });

    expect(deleteMutate).toHaveBeenCalledWith({ id: 42, preferenceId: mockPreferenceWithId.id });
  });

  it('an asking category offers Ask me / Always allow / Never and both lists (#4187)', async () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);
    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });
    await waitFor(() => screen.getByText('Makeovers & Styling'));
    const row = screen.getByText('Makeovers & Styling').closest('[data-testid="category-row"]');
    expect(row).not.toBeNull();
    const labels = Array.from(row!.querySelectorAll('option')).map((o) => o.textContent);
    expect(labels).toEqual(['Default (Ask me)', 'Ask me', 'Always allow', 'Never']);
    expect(row!.textContent).toMatch(/allow list skip the ask/i);
  });

  it('a social category does not offer Ask me (#4187)', async () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);
    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });
    await waitFor(() => screen.getByText('Hostile'));
    const row = screen.getByText('Hostile').closest('[data-testid="category-row"]');
    const labels = Array.from(row!.querySelectorAll('option')).map((o) => o.textContent);
    expect(labels).not.toContain('Ask me');
    expect(labels).not.toContain('Ask me each time');
    expect(labels).toContain('Allowlist only');
  });

  it('offers the rivals mode option (#2170)', async () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);
    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });
    await waitFor(() => screen.getByText('Romantic'));
    // The rivals mode is selectable in the per-category picker.
    expect(screen.getAllByText('My declared rivals').length).toBeGreaterThan(0);
  });

  it('calls useAddBlacklist when barring a character under all_but_blacklist mode', async () => {
    const { addBlacklistMutate } = setupDefaultMocks();

    // Pre-set the Romantic category rule to "all_but_blacklist" so BlacklistManager is visible.
    vi.mocked(queries.useCategoryRules).mockReturnValue({
      data: {
        count: 1,
        results: [{ id: 99, preference: 5, category: 10, mode: 'all_but_blacklist' }],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useCategoryRules>);

    vi.mocked(mailQueries.useTenureSearch).mockReturnValue({
      data: { count: 1, results: [{ id: 7, display_name: 'Zara' }] },
      isLoading: false,
    } as unknown as ReturnType<typeof mailQueries.useTenureSearch>);

    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => romanticRow().getByPlaceholderText('Search character to bar...'));

    const zaraButton = await romanticRow().findByRole('button', { name: 'Zara' });
    await userEvent.click(zaraButton);

    expect(addBlacklistMutate).toHaveBeenCalledWith(
      { owner_tenure: 1, blocked_tenure: 7, category: 10 },
      expect.any(Object)
    );
  });

  // -------------------------------------------------------------------------
  // Add whitelist entry calls useAddWhitelist
  // -------------------------------------------------------------------------

  it('calls useAddWhitelist when adding a character to the allowlist', async () => {
    const { addMutate } = setupDefaultMocks();

    // Pre-set the Romantic category rule to "allowlist" so WhitelistManager is visible
    vi.mocked(queries.useCategoryRules).mockReturnValue({
      data: {
        count: 1,
        results: [{ id: 99, preference: 5, category: 10, mode: 'allowlist' }],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useCategoryRules>);

    // Return a search result for the tenure search
    vi.mocked(mailQueries.useTenureSearch).mockReturnValue({
      data: { count: 1, results: [{ id: 7, display_name: 'Zara' }] },
      isLoading: false,
    } as unknown as ReturnType<typeof mailQueries.useTenureSearch>);

    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => romanticRow().getByPlaceholderText('Search character to add...'));

    // Click "Zara" in the dropdown
    const zaraButton = await romanticRow().findByRole('button', { name: 'Zara' });
    await userEvent.click(zaraButton);

    expect(addMutate).toHaveBeenCalledWith(
      { owner_tenure: 1, allowed_tenure: 7, category: 10 },
      expect.any(Object)
    );
  });

  // -------------------------------------------------------------------------
  // Remove whitelist entry calls useRemoveWhitelist
  // -------------------------------------------------------------------------

  it('calls useRemoveWhitelist when removing a character chip', async () => {
    const { removeMutate } = setupDefaultMocks();

    // Pre-set the Romantic category to allowlist mode, with one whitelist entry
    vi.mocked(queries.useCategoryRules).mockReturnValue({
      data: {
        count: 1,
        results: [{ id: 99, preference: 5, category: 10, mode: 'allowlist' }],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useCategoryRules>);

    vi.mocked(queries.useWhitelist).mockReturnValue({
      data: {
        count: 1,
        results: [
          {
            id: 55,
            owner_tenure: 1,
            allowed_tenure: 7,
            allowed_tenure_name: '1st player of Zara',
            category: 10,
            added_at: '2026-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useWhitelist>);

    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => romanticRow().getByLabelText('Remove 1st player of Zara from allowlist'));

    await userEvent.click(romanticRow().getByLabelText('Remove 1st player of Zara from allowlist'));

    expect(removeMutate).toHaveBeenCalledWith({
      id: 55,
      ownerTenureId: 1,
      categoryId: 10,
    });
  });

  // -------------------------------------------------------------------------
  // Character switch triggers refetch (hooks called with new tenureId)
  // -------------------------------------------------------------------------

  it('passes the new tenureId to hooks when character selection changes', async () => {
    setupDefaultMocks();
    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => {
      expect(vi.mocked(queries.useConsentPreference)).toHaveBeenCalledWith(1);
    });

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '2' } });

    await waitFor(() => {
      expect(vi.mocked(queries.useConsentPreference)).toHaveBeenCalledWith(2);
    });
  });

  // -------------------------------------------------------------------------
  // Preference row created before category rule when no persisted row exists
  // -------------------------------------------------------------------------

  it('calls createPreference before updating allow_social_actions when no id exists', async () => {
    const { createMutateAsync, updateMutate } = setupDefaultMocks();

    // Simulate synthesised preference (no id)
    vi.mocked(queries.useConsentPreference).mockReturnValue({
      data: mockPreferenceNoId,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useConsentPreference>);

    createMutateAsync.mockResolvedValue({ id: 99, tenure: 1, allow_social_actions: true });

    renderWithProviders(<PrivacyPage />);

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: '1' } });

    await waitFor(() => screen.getByLabelText('Pause all social targeting'));

    await userEvent.click(screen.getByLabelText('Pause all social targeting'));

    await waitFor(() => {
      expect(createMutateAsync).toHaveBeenCalledWith({ tenure: 1 });
      expect(updateMutate).toHaveBeenCalledWith({ id: 99, body: { allow_social_actions: false } });
    });
  });
});
