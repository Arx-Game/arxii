import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PlaceClueDialog } from './PlaceClueDialog';

// AuthorClueDialog (#3432, "New clue…") is exercised in its own test file —
// only its hook dependencies are mocked here so it renders for real and this
// file can prove the mint-then-place handoff (onCreated pre-fills the slug).
const authorClueMutate = vi.fn();

vi.mock('@/clues/queries', () => ({
  useAuthorClueMutation: vi.fn(() => ({ mutate: authorClueMutate, isPending: false })),
}));
vi.mock('@/world-builder/useWorldBuilderActor', () => ({
  useWorldBuilderActor: vi.fn(() => 42),
}));
vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => ({ is_staff: true })),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function renderDialog(overrides: Partial<Parameters<typeof PlaceClueDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <PlaceClueDialog
      roomId={5}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('PlaceClueDialog', () => {
  it('dispatches staff_place_clue with the room id, clue slug, and difficulty', async () => {
    const { runAction } = renderDialog();

    await userEvent.type(screen.getByLabelText(/clue slug/i), 'torn-letter');
    await userEvent.clear(screen.getByLabelText(/detect difficulty/i));
    await userEvent.type(screen.getByLabelText(/detect difficulty/i), '5');
    await userEvent.click(screen.getByTestId('place-clue-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_clue', {
      room_id: 5,
      clue_slug: 'torn-letter',
      detect_difficulty: 5,
    });
  });

  it('keeps the submit button disabled until a clue slug is entered', () => {
    renderDialog();
    expect(screen.getByTestId('place-clue-submit')).toBeDisabled();
  });

  it('dispatches staff_place_clue_trigger with the room id and clue slug in passive mode', async () => {
    const { runAction } = renderDialog();

    await userEvent.click(screen.getByRole('tab', { name: /on entry \(passive\)/i }));
    await userEvent.type(screen.getByLabelText(/clue slug/i), 'whisper');
    await userEvent.click(screen.getByTestId('place-clue-submit'));

    expect(runAction).toHaveBeenCalledWith('staff_place_clue_trigger', {
      room_id: 5,
      clue_slug: 'whisper',
    });
  });

  it('hides the detect-difficulty input in passive mode', async () => {
    renderDialog();

    await userEvent.click(screen.getByRole('tab', { name: /on entry \(passive\)/i }));

    expect(screen.queryByLabelText(/detect difficulty/i)).not.toBeInTheDocument();
  });

  it('pre-fills the clue slug from AuthorClueDialog on a successful "New clue…" mint', () => {
    authorClueMutate.mockImplementation((_kwargs, opts) => {
      opts.onSuccess({ success: true, message: 'Clue authored.', data: { slug: 'torn-letter-2' } });
    });
    renderDialog();

    fireEvent.click(screen.getByText('New clue…'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Torn Letter' } });
    fireEvent.change(screen.getByLabelText('Clue text'), { target: { value: 'A letter.' } });
    fireEvent.change(screen.getByLabelText('Target id'), { target: { value: '1' } });
    fireEvent.click(screen.getByTestId('author-clue-submit'));

    expect(screen.getByLabelText(/clue slug/i)).toHaveValue('torn-letter-2');
  });
});
