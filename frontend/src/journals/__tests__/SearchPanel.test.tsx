/**
 * SearchPanel tests (#3941) — the finding options and the index under them.
 *
 * The panel is not a mode: closed, it renders nothing readable; open, it shows
 * the four groups plus the index of the rows the page already has. It derives
 * its "About someone" and "Tags" lists from those same rows, so it needs no
 * endpoint and no provider of its own.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SearchPanel } from '../components/SearchPanel';

const rows = [
  {
    id: 1,
    author: 10,
    author_name: 'Corvin Ashe',
    title: 'Third correction',
    body: 'A third time, then, and plainly.',
    kind: 'entry' as const,
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-09-18T00:00:00Z',
    edited_at: null,
    tags: [{ id: 1, name: 'council' }],
    response_count: 1,
    posthumous_override: 'inherit' as const,
    revealed_at: null,
    is_posthumous: false,
    about: 20,
    about_name: 'Ilsavet du Verane',
    author_persona_id: 1,
    ic_timestamp: null,
    can_retort: false,
    is_own: false,
  },
];

describe('SearchPanel (#3941)', () => {
  it('renders nothing when closed', () => {
    render(
      <SearchPanel
        open={false}
        filters={{}}
        onFiltersChange={vi.fn()}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={4}
        visitedAt={null}
      />
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows the groups, the count, the index, and opens a row', () => {
    const onOpen = vi.fn();
    const onFilters = vi.fn();
    render(
      <SearchPanel
        open
        filters={{}}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={onOpen}
        isStaff={true}
        sinceVisitCount={4}
        visitedAt="2026-09-16T08:00:00Z"
      />
    );
    expect(screen.getByText(/Since your last visit/)).toHaveTextContent('4');
    expect(screen.getByText('Post mortems')).toBeInTheDocument();
    expect(screen.getByText('Black journals only')).toBeInTheDocument();
    expect(screen.getByText('Ilsavet du Verane')).toBeInTheDocument(); // About someone
    expect(screen.getByText('council')).toBeInTheDocument(); // Tags
    fireEvent.click(screen.getByText('Third correction'));
    expect(onOpen).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByText('Introductions'));
    expect(onFilters).toHaveBeenCalledWith(expect.objectContaining({ kind: 'introductions' }));
  });

  it('lets a chosen subject or tag be unchosen, and Newest clears everything', () => {
    const onFilters = vi.fn();
    const { rerender } = render(
      <SearchPanel
        open
        filters={{ about: 20 }}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={0}
        visitedAt={null}
      />
    );

    // The live subject is pressed, and pressing it again is the way back out.
    const subject = screen.getByRole('button', { name: 'Ilsavet du Verane · 1' });
    expect(subject).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(subject);
    expect(onFilters).toHaveBeenCalledWith(expect.objectContaining({ about: undefined }));

    onFilters.mockClear();
    rerender(
      <SearchPanel
        open
        filters={{ tag: 'council' }}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={0}
        visitedAt={null}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'council' }));
    expect(onFilters).toHaveBeenCalledWith(expect.objectContaining({ tag: undefined }));

    onFilters.mockClear();
    rerender(
      <SearchPanel
        open
        filters={{ about: 20, tag: 'council', writer: 'Corvin', post_mortem: 1, page: 3 }}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={0}
        visitedAt={null}
      />
    );
    fireEvent.click(screen.getByText('Newest'));
    expect(onFilters).toHaveBeenCalledWith({ page: 3 });
  });

  it('cuts on the visit it was given, and on nothing when there was no visit', () => {
    const onFilters = vi.fn();
    const { rerender } = render(
      <SearchPanel
        open
        filters={{}}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={4}
        visitedAt="2026-09-16T08:00:00Z"
      />
    );
    fireEvent.click(screen.getByText(/Since your last visit/));
    expect(onFilters).toHaveBeenCalledWith(
      expect.objectContaining({ since: '2026-09-16T08:00:00Z' })
    );

    // A reader with no previous visit: the option narrows nothing, because nothing in
    // front of them is old.
    onFilters.mockClear();
    rerender(
      <SearchPanel
        open
        filters={{}}
        onFiltersChange={onFilters}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={4}
        visitedAt={null}
      />
    );
    fireEvent.click(screen.getByText(/Since your last visit/));
    expect(onFilters).toHaveBeenCalledWith(expect.objectContaining({ since: undefined }));
  });

  it('marks the live option when a since cut holds', () => {
    render(
      <SearchPanel
        open
        filters={{ since: '2026-09-16T08:00:00Z' }}
        onFiltersChange={vi.fn()}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={4}
        visitedAt="2026-09-16T08:00:00Z"
      />
    );
    expect(screen.getByText(/Since your last visit/)).toHaveAttribute('aria-current', 'true');
    expect(screen.getByText('Newest')).not.toHaveAttribute('aria-current');
  });

  it('hides the staff filter for players', () => {
    render(
      <SearchPanel
        open
        filters={{}}
        onFiltersChange={vi.fn()}
        rows={rows}
        onOpenEntry={vi.fn()}
        isStaff={false}
        sinceVisitCount={0}
        visitedAt={null}
      />
    );
    expect(screen.queryByText('Black journals only')).not.toBeInTheDocument();
  });
});
