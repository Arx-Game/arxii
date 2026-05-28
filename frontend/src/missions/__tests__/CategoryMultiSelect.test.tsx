import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { CategoryMultiSelect } from '../components/CategoryMultiSelect';
import * as queries from '../queries';

// UseQueryResult has ~25 required fields. Cast through unknown to avoid
// spelling out every field in mock objects.
type MockQueryResult = ReturnType<typeof queries.useMissionCategories>;

describe('CategoryMultiSelect', () => {
  it('renders an empty state when there are no categories', () => {
    vi.spyOn(queries, 'useMissionCategories').mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
      isError: false,
    } as unknown as MockQueryResult);

    render(<CategoryMultiSelect value={[]} onChange={() => {}} />);
    expect(screen.getByText(/no categories available/i)).toBeInTheDocument();
  });

  it('renders categories from query and toggles selection', () => {
    vi.spyOn(queries, 'useMissionCategories').mockReturnValue({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [
          { id: 1, name: 'courtly', description: '', display_order: 1 },
          { id: 2, name: 'heist', description: '', display_order: 2 },
        ],
      },
      isLoading: false,
      isError: false,
    } as unknown as MockQueryResult);

    const onChange = vi.fn();
    render(<CategoryMultiSelect value={[]} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText('courtly'));
    expect(onChange).toHaveBeenCalledWith([1]);
  });

  it('removes a category when its checkbox is toggled off', () => {
    vi.spyOn(queries, 'useMissionCategories').mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [{ id: 1, name: 'courtly', description: '', display_order: 1 }],
      },
      isLoading: false,
      isError: false,
    } as unknown as MockQueryResult);

    const onChange = vi.fn();
    render(<CategoryMultiSelect value={[1]} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText('courtly'));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
