/**
 * EditGMProfileDialog tests (#3478 fix round — Finding 2). Mirrors
 * `stories/__tests__/StoryFormDialog.test.tsx`'s convention: mock the owning
 * query module's read + mutation hooks directly and drive the mutation
 * mock's `onSuccess` callback to exercise the dialog's success path.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EditGMProfileDialog } from '../EditGMProfileDialog';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

interface MockMineData {
  id: number;
  level: string;
  level_display: string;
  contact_times?: string;
  ooc_info?: string;
}

let mockMineData: MockMineData | undefined = {
  id: 1,
  level: 'apprentice',
  level_display: 'Apprentice',
  contact_times: 'Weeknights, US evening',
  ooc_info: 'New to GMing, be gentle.',
};
const saveMock = vi.fn();
let saveIsPending = false;

vi.mock('../queries', () => ({
  useGMProfileMineQuery: () => ({ data: mockMineData, isLoading: false, isError: false }),
  useUpdateGMProfileMineMutation: () => ({ mutate: saveMock, isPending: saveIsPending }),
}));

describe('EditGMProfileDialog', () => {
  afterEach(() => {
    saveIsPending = false;
    mockMineData = {
      id: 1,
      level: 'apprentice',
      level_display: 'Apprentice',
      contact_times: 'Weeknights, US evening',
      ooc_info: 'New to GMing, be gentle.',
    };
    vi.clearAllMocks();
  });

  it('prefills contact times and OOC info from the loaded profile', () => {
    renderWithProviders(<EditGMProfileDialog open onOpenChange={vi.fn()} />);

    expect((screen.getByLabelText(/contact times/i) as HTMLTextAreaElement).value).toBe(
      'Weeknights, US evening'
    );
    expect((screen.getByLabelText(/ooc info/i) as HTMLTextAreaElement).value).toBe(
      'New to GMing, be gentle.'
    );
  });

  it('saving submits the edited contact_times/ooc_info to the PATCH mutation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EditGMProfileDialog open onOpenChange={vi.fn()} />);

    const contactTimes = screen.getByLabelText(/contact times/i);
    await user.clear(contactTimes);
    await user.type(contactTimes, 'Weekends only');

    const oocInfo = screen.getByLabelText(/ooc info/i);
    await user.clear(oocInfo);
    await user.type(oocInfo, 'Ask before heavy topics.');

    await user.click(screen.getByTestId('edit-gm-profile-save'));

    expect(saveMock).toHaveBeenCalledWith(
      { contact_times: 'Weekends only', ooc_info: 'Ask before heavy topics.' },
      expect.any(Object)
    );
  });

  it('closes the dialog when the save mutation succeeds', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    saveMock.mockImplementation((_data: unknown, callbacks: { onSuccess?: () => void }) =>
      callbacks.onSuccess?.()
    );
    renderWithProviders(<EditGMProfileDialog open onOpenChange={onOpenChange} />);

    await user.click(screen.getByTestId('edit-gm-profile-save'));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables Save while the mutation is pending', () => {
    saveIsPending = true;
    renderWithProviders(<EditGMProfileDialog open onOpenChange={vi.fn()} />);

    expect(screen.getByTestId('edit-gm-profile-save')).toBeDisabled();
  });
});
