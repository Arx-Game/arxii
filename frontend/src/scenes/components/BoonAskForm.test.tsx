import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { BoonAskForm } from './BoonAskForm';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { BoonOptions } from '../actionTypes';

const { fetchBoonOptions } = vi.hoisted(() => ({
  fetchBoonOptions: vi.fn(),
}));

vi.mock('../actionQueries', () => ({
  fetchBoonOptions,
}));

// jsdom can't drive Radix Select's popover/pointer-capture interactions —
// mirrors the mock pattern used by other tests over @/components/ui/select
// (e.g. stories/__tests__/SubjectRefFields.test.tsx).
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
  }) => (
    <select
      aria-label="material category"
      value={value ?? ''}
      onChange={(e) => onValueChange?.(e.target.value)}
    >
      <option value="" disabled>
        Choose a crafting category…
      </option>
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

const EMPTY_OPTIONS: BoonOptions = {
  sum_tiers: [],
  material_categories: [],
  pointer_items: [],
};

describe('BoonAskForm', () => {
  beforeEach(() => {
    fetchBoonOptions.mockReset();
  });

  it('confirms a money ask with the selected tier', async () => {
    fetchBoonOptions.mockResolvedValue({
      ...EMPTY_OPTIONS,
      sum_tiers: [
        { tier: 'minor', label: 'Minor', coppers: 50 },
        { tier: 'fair', label: 'Fair', coppers: 200 },
      ],
    });
    const onConfirm = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        targetName="Corwin"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    await waitFor(() => expect(screen.getByText('Fair')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Fair'));
    fireEvent.click(screen.getByRole('button', { name: /make the ask/i }));

    expect(onConfirm).toHaveBeenCalledWith({ kind: 'money', sum_tier: 'fair' });
    expect(fetchBoonOptions).toHaveBeenCalledWith(7, 3);
  });

  it('disables the money kind and shows a fallback when the target is penniless', async () => {
    fetchBoonOptions.mockResolvedValue(EMPTY_OPTIONS);
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );

    await waitFor(() =>
      expect(screen.getByText(/they have nothing worth asking for/i)).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: 'Money' })).toBeDisabled();
  });

  it('confirms a material ask with the chosen category and tier', async () => {
    fetchBoonOptions.mockResolvedValue({
      ...EMPTY_OPTIONS,
      material_categories: [
        { id: 1, name: 'Precious Gemstones' },
        { id: 2, name: 'Rare Metals' },
      ],
    });
    const onConfirm = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Materials' }));
    await waitFor(() => expect(screen.getByLabelText('material category')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('material category'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Great' }));
    fireEvent.click(screen.getByRole('button', { name: /make the ask/i }));

    expect(onConfirm).toHaveBeenCalledWith({
      kind: 'material',
      sum_tier: 'great',
      material_category_id: 2,
    });
  });

  it('lists held pointer-known items and confirms the chosen one', async () => {
    fetchBoonOptions.mockResolvedValue({
      ...EMPTY_OPTIONS,
      pointer_items: [
        { item_instance_id: 11, name: 'a silver signet ring', source: 'held' },
        { item_instance_id: 12, name: 'a locked strongbox', source: 'vault' },
      ],
    });
    const onConfirm = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'A held item' }));
    await waitFor(() => expect(screen.getByText('a silver signet ring')).toBeInTheDocument());
    expect(screen.queryByText('a locked strongbox')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('a silver signet ring'));
    fireEvent.click(screen.getByRole('button', { name: /make the ask/i }));

    expect(onConfirm).toHaveBeenCalledWith({ kind: 'held_item', item_instance_id: 11 });
  });

  it('lists vault pointer-known items separately from held items', async () => {
    fetchBoonOptions.mockResolvedValue({
      ...EMPTY_OPTIONS,
      pointer_items: [
        { item_instance_id: 11, name: 'a silver signet ring', source: 'held' },
        { item_instance_id: 12, name: 'a locked strongbox', source: 'vault' },
      ],
    });
    const onConfirm = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'From a vault' }));
    await waitFor(() => expect(screen.getByText('a locked strongbox')).toBeInTheDocument());
    expect(screen.queryByText('a silver signet ring')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('a locked strongbox'));
    fireEvent.click(screen.getByRole('button', { name: /make the ask/i }));

    expect(onConfirm).toHaveBeenCalledWith({ kind: 'vault_item', item_instance_id: 12 });
  });

  it('shows the neutral pointer-empty message and stays unconfirmable when nothing is known', async () => {
    fetchBoonOptions.mockResolvedValue(EMPTY_OPTIONS);
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'A held item' }));
    await waitFor(() =>
      expect(screen.getByText('PLACEHOLDER: you know of nothing they hold.')).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /make the ask/i })).toBeDisabled();
  });

  it('confirms a deed ask with the entered text', async () => {
    fetchBoonOptions.mockResolvedValue(EMPTY_OPTIONS);
    const onConfirm = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'A deed' }));
    fireEvent.change(screen.getByPlaceholderText('The deed you ask of them…'), {
      target: { value: 'Guard the gate' },
    });
    fireEvent.click(screen.getByRole('button', { name: /make the ask/i }));

    expect(onConfirm).toHaveBeenCalledWith({ kind: 'deed', deed_text: 'Guard the gate' });
  });

  it('calls onCancel when cancel is clicked', async () => {
    fetchBoonOptions.mockResolvedValue(EMPTY_OPTIONS);
    const onCancel = vi.fn();
    renderWithProviders(
      <BoonAskForm
        targetPersonaId={7}
        initiatorPersonaId={3}
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
