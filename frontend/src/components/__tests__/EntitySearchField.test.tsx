/**
 * EntitySearchField — debounced search-and-select field tests (#882).
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { EntitySearchField, type EntitySearchResult } from '../EntitySearchField';

const ROOM: EntitySearchResult = { id: 7, name: 'Notice Board Plaza', hint: 'Test District' };

describe('EntitySearchField', () => {
  it('searches after 2+ characters and lists results with their hint', async () => {
    const user = userEvent.setup();
    const search = vi.fn().mockResolvedValue([ROOM]);
    render(<EntitySearchField value={null} onChange={vi.fn()} search={search} label="Target" />);

    await user.type(screen.getByLabelText('Target'), 'Notice');

    await waitFor(() => expect(search).toHaveBeenCalledWith('Notice'), { timeout: 2000 });
    expect(await screen.findByText(/Notice Board Plaza/)).toBeInTheDocument();
    expect(screen.getByText(/Test District/)).toBeInTheDocument();
  });

  it('calls onChange with the selected id and fills the input with its name', async () => {
    const user = userEvent.setup();
    const search = vi.fn().mockResolvedValue([ROOM]);
    const onChange = vi.fn();
    render(<EntitySearchField value={null} onChange={onChange} search={search} label="Target" />);

    await user.type(screen.getByLabelText('Target'), 'Notice');
    const option = await screen.findByText(/Notice Board Plaza/);
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith(7);
    expect(screen.getByLabelText('Target')).toHaveValue('Notice Board Plaza');
  });

  it('clears the selection when the user edits the input after selecting', async () => {
    const user = userEvent.setup();
    const search = vi.fn().mockResolvedValue([ROOM]);
    const onChange = vi.fn();
    render(<EntitySearchField value={null} onChange={onChange} search={search} label="Target" />);

    await user.type(screen.getByLabelText('Target'), 'Notice');
    await user.click(await screen.findByText(/Notice Board Plaza/));
    onChange.mockClear();

    await user.type(screen.getByLabelText('Target'), 'x');

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('resolves and displays an existing value on mount via resolveById', async () => {
    const resolveById = vi.fn().mockResolvedValue(ROOM);
    render(
      <EntitySearchField
        value={7}
        onChange={vi.fn()}
        search={vi.fn().mockResolvedValue([])}
        resolveById={resolveById}
        label="Target"
      />
    );

    await waitFor(() => expect(resolveById).toHaveBeenCalledWith(7));
    expect(await screen.findByDisplayValue('Notice Board Plaza')).toBeInTheDocument();
  });
});
