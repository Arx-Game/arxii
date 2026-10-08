/**
 * FacetPicker (#4197): search what exists, see what a new spelling is near before anything
 * is made, and, for staff only, create it in the same gesture.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FacetPicker } from '../FacetPicker';
import { facetKey } from '../../facetKey';

const near = vi.fn();
const create = vi.fn();
vi.mock('@/character-creation/api', () => ({
  getNearFacets: (name: string) => near(name),
  createFacet: (name: string) => create(name),
}));
vi.mock('@/hooks/useDebouncedValue', () => ({ useDebouncedValue: (value: string) => value }));

const FACETS = [
  { id: 1, name: 'Scythe', description: '' },
  { id: 2, name: 'Silk', description: '' },
];

function renderPicker(props: Partial<React.ComponentProps<typeof FacetPicker>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onPick = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <FacetPicker facets={FACETS} onPick={onPick} {...props} />
    </QueryClientProvider>
  );
  return { onPick };
}

describe('facetKey', () => {
  it('collapses case, punctuation and the last word plural', () => {
    expect(facetKey('Scythes')).toBe('scythe');
    expect(facetKey('Scythe-like Weapons')).toBe('scythe like weapon');
    expect(facetKey('Butterflies')).toBe('butterfly');
    expect(facetKey('Glass')).toBe('glass');
  });
});

describe('FacetPicker', () => {
  beforeEach(() => {
    near.mockReset();
    create.mockReset();
  });

  it('picks an existing facet by search', async () => {
    const { onPick } = renderPicker();
    await userEvent.click(screen.getByRole('button', { name: '+ Add facet' }));
    await userEvent.type(screen.getByLabelText('Add facet'), 'sil');
    await userEvent.click(screen.getByText('Silk'));
    expect(onPick).toHaveBeenCalledWith(FACETS[1]);
  });

  it('shows what a new spelling is near and offers staff to create it', async () => {
    // A near-match whose key differs: the server would not answer it for "Sickles".
    near.mockResolvedValue([{ id: 3, name: 'Sickle Blade', description: '' }]);
    create.mockResolvedValue({ id: 9, name: 'Sickles', description: '', matched: false });
    const { onPick } = renderPicker({ canCreate: true });
    await userEvent.click(screen.getByRole('button', { name: '+ Add facet' }));
    await userEvent.type(screen.getByLabelText('Add facet'), 'Sickles');
    await waitFor(() => expect(screen.getByText('Did you mean')).toBeInTheDocument());
    expect(screen.getByText('Sickle Blade')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Create “Sickles”'));
    await waitFor(() => expect(create).toHaveBeenCalledWith('Sickles'));
    await waitFor(() =>
      expect(onPick).toHaveBeenCalledWith({
        id: 9,
        name: 'Sickles',
        description: '',
        matched: false,
      })
    );
  });

  it('never offers a player the create item', async () => {
    near.mockResolvedValue([]);
    renderPicker({ canCreate: false });
    await userEvent.click(screen.getByRole('button', { name: '+ Add facet' }));
    await userEvent.type(screen.getByLabelText('Add facet'), 'Granite');
    await waitFor(() => expect(near).toHaveBeenCalledWith('Granite'));
    expect(screen.queryByText(/Create/)).not.toBeInTheDocument();
  });

  it('does not offer to create a spelling that already resolves', async () => {
    renderPicker({ canCreate: true });
    await userEvent.click(screen.getByRole('button', { name: '+ Add facet' }));
    await userEvent.type(screen.getByLabelText('Add facet'), 'scythes');
    expect(screen.getByText('Scythe')).toBeInTheDocument();
    expect(screen.queryByText(/Create/)).not.toBeInTheDocument();
    expect(near).not.toHaveBeenCalledWith('scythes');
  });
});
