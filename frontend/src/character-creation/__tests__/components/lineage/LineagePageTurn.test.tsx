/**
 * The foot of the Lineage stage (#5146): Back, "Restart: Clear All Choices", Next, as
 * three buttons of one style; Restart asks before it empties the life.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import * as api from '../../../api';
import { LineagePageTurn } from '../../../components/lineage/LineagePageTurn';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

vi.mock('../../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api')>()),
  clearLife: vi.fn(),
}));

const draft = createMockDraft();
const back = { label: 'Back: Heritage', onClick: vi.fn() };
const next = { label: 'Next: Path', onClick: vi.fn() };
const restart = () => screen.getByRole('button', { name: 'Restart: Clear All Choices' });

describe('LineagePageTurn', () => {
  beforeEach(() => {
    vi.mocked(api.clearLife).mockReset();
    vi.mocked(api.clearLife).mockResolvedValue(draft);
  });

  it('reads Back, Restart: Clear All Choices, Next, three buttons of one style', () => {
    const { container } = renderWithCharacterCreationProviders(
      <LineagePageTurn draft={draft} copy={{}} back={back} next={next} />
    );
    const doors = within(container.querySelector('.page-turn') as HTMLElement).getAllByRole(
      'button'
    );
    expect(doors.map((door) => door.textContent)).toEqual([
      'Back: Heritage',
      'Restart: Clear All Choices',
      'Next: Path',
    ]);
    expect(new Set(doors.map((door) => door.className))).toEqual(new Set(['btn']));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('Restart asks first, and Cancel clears nothing', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <LineagePageTurn draft={draft} copy={{}} back={back} next={next} />
    );
    await user.click(restart());
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('heading')).toHaveTextContent('Restart: Clear All Choices');
    expect(dialog).toHaveTextContent(
      'This removes every choice under Life So Far. Your family and the other stages are kept.'
    );
    expect(api.clearLife).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.clearLife).not.toHaveBeenCalled();
  });

  it('confirming sends one clear for this draft and closes the dialog', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <LineagePageTurn draft={draft} copy={{}} back={back} next={next} />
    );
    await user.click(restart());
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear all choices' })
    );
    await waitFor(() => expect(api.clearLife).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.clearLife).mock.calls[0][0]).toBe(draft.id);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(restart()).toBeEnabled());
  });

  it('the door waits while a clear is in flight', async () => {
    let answer: (value: typeof draft) => void = () => undefined;
    vi.mocked(api.clearLife).mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      })
    );
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <LineagePageTurn draft={draft} copy={{}} back={back} next={next} />
    );
    await user.click(restart());
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear all choices' })
    );
    await waitFor(() => expect(restart()).toBeDisabled());
    answer(draft);
    await waitFor(() => expect(restart()).toBeEnabled());
  });

  it("staff's own words for the door replace the default", () => {
    renderWithCharacterCreationProviders(
      <LineagePageTurn
        draft={draft}
        copy={{ life_restart_label: 'Clear this life', beats_start_blank: 'Start blank' }}
        back={back}
        next={next}
      />
    );
    expect(screen.getByRole('button', { name: 'Clear this life' })).toBeInTheDocument();
    expect(screen.queryByText('Start blank')).not.toBeInTheDocument();
  });
});
