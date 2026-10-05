import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { fetchTargetMenu, TargetMenuFetchError } from './targetMenuApi';
import { TargetMenuInputs } from './TargetMenuInputs';

vi.mock('./targetMenuApi', async () => {
  const actual = await vi.importActual<typeof import('./targetMenuApi')>('./targetMenuApi');
  return { ...actual, fetchTargetMenu: vi.fn() };
});

const mockFetch = vi.mocked(fetchTargetMenu);
const entry = {
  key: 'give',
  label: 'Give',
  group: 'items',
  ref: { backend: 'registry', registry_key: 'give' },
  kwargs: { menu_target: { kind: 'items', target_id: 9 } },
  available: true,
  reasons: [],
  inputs: [
    {
      name: 'recipient_persona_id',
      kind: 'recipient',
      required: true,
      target_kind: null,
      default: null,
    },
  ],
  candidates: [
    { key: '14', label: 'Ari', kwargs: { recipient_persona_id: 14 }, available: true, reasons: [] },
    {
      key: '15',
      label: 'Bryn',
      kwargs: { recipient_persona_id: 15 },
      available: false,
      reasons: ['They have left.'],
    },
  ],
  action: null,
  risk: null,
};

const refreshedMenu = {
  actor_id: 7,
  target: { kind: 'items' as const, target_id: 9 },
  label: 'silver cup',
  groups: [{ key: 'items', label: 'Item handling' }],
  entries: [entry],
};

describe('TargetMenuInputs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue(refreshedMenu);
  });

  it('shows visible blocked reasons, starts with an eligible candidate, and sends only the chosen server kwargs', async () => {
    const onConfirm = vi.fn(() => true);
    renderWithProviders(
      <TargetMenuInputs
        partition="account-1"
        actorId={7}
        target={{ kind: 'items', target_id: 9 }}
        entry={entry}
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    );

    expect(await screen.findByRole('option', { name: 'Ari' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Bryn.*They have left/ })).toBeDisabled();
    expect(screen.getByRole('combobox')).toHaveValue('14');
    fireEvent.click(screen.getByRole('button', { name: 'Give' }));
    expect(onConfirm).toHaveBeenCalledWith({
      menu_target: { kind: 'items', target_id: 9 },
      recipient_persona_id: 14,
    });
  });

  it('loads and appends the next cursor page without losing earlier choices', async () => {
    const firstPage = {
      ...refreshedMenu,
      entries: [{ ...entry, next_candidate_cursor: 'cursor-2' }],
    };
    const secondPage = {
      ...refreshedMenu,
      entries: [
        {
          ...entry,
          candidates: [
            {
              key: '16',
              label: 'Caro',
              kwargs: { recipient_persona_id: 16 },
              available: true,
              reasons: [],
            },
          ],
          next_candidate_cursor: null,
        },
      ],
    };
    mockFetch.mockImplementation(async (_actor, _target, _signal, _inputsFor, cursor) =>
      cursor === undefined ? firstPage : secondPage
    );
    const onConfirm = vi.fn(() => true);
    renderWithProviders(
      <TargetMenuInputs
        partition="account-1"
        actorId={7}
        target={{ kind: 'items', target_id: 9 }}
        entry={entry}
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    );

    expect(await screen.findByRole('option', { name: 'Ari' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load more choices' }));
    expect(await screen.findByRole('option', { name: 'Caro' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '16' } });
    fireEvent.click(screen.getByRole('button', { name: 'Give' }));
    expect(onConfirm).toHaveBeenCalledWith({
      menu_target: { kind: 'items', target_id: 9 },
      recipient_persona_id: 16,
    });
    expect(mockFetch).toHaveBeenCalledWith(
      7,
      { kind: 'items', target_id: 9 },
      expect.any(AbortSignal),
      'give',
      'cursor-2'
    );
  });

  it('shows the server retry delay when choice refresh is rate limited', async () => {
    mockFetch.mockRejectedValueOnce(new TargetMenuFetchError('throttled', 429, 17));
    renderWithProviders(
      <TargetMenuInputs
        partition="account-1"
        actorId={7}
        target={{ kind: 'items', target_id: 9 }}
        entry={entry}
        open
        onOpenChange={vi.fn()}
        onConfirm={vi.fn(() => true)}
      />
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 17 seconds.');
    expect(screen.getByRole('button', { name: 'Give' })).toBeDisabled();
  });

  it('does not permit confirmation when no candidate is eligible', async () => {
    mockFetch.mockResolvedValue({
      ...refreshedMenu,
      entries: [
        {
          ...entry,
          candidates: entry.candidates.map((candidate) => ({ ...candidate, available: false })),
        },
      ],
    });
    const onConfirm = vi.fn(() => true);
    renderWithProviders(
      <TargetMenuInputs
        partition="account-1"
        actorId={7}
        target={{ kind: 'items', target_id: 9 }}
        entry={entry}
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    );
    expect(await screen.findByRole('button', { name: 'Give' })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('does not allow stale choices when the deliberate refresh fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network unavailable'));
    const onConfirm = vi.fn(() => true);
    renderWithProviders(
      <TargetMenuInputs
        partition="account-1"
        actorId={7}
        target={{ kind: 'items', target_id: 9 }}
        entry={entry}
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load current choices');
    expect(screen.getByRole('button', { name: 'Give' })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
