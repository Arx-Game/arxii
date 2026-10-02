import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { GMPrompt } from '../../types';

const mutateAsync = vi.fn();

vi.mock('../../gmPromptQueries', async (orig) => ({
  ...(await orig<typeof import('../../gmPromptQueries')>()),
  useNarrateGMPrompt: () => ({ mutateAsync, isPending: false }),
}));

import { NarrationComposer } from '../NarrationComposer';

const crossing: GMPrompt = {
  id: 7,
  kind: 'crossing',
  kind_label: 'Crossing',
  status: 'pending',
  scene: 1,
  character_sheet: 3,
  subject_name: 'Rowan Ashcombe',
  subject_persona_id: 30,
  moment_type: null,
  moment_type_label: '',
  technique_name: '',
  stake_summary: '',
  room_text: 'room',
  private_text: 'vision',
  prepared_for_character: true,
  created_at: '2026-10-02T00:00:00Z',
};

// A kind with no authored private_text (e.g. a stake outcome) -- #4101 Task 10
// fix round 1, Important finding 1: every kind still gets a private send.
const stakeOutcome: GMPrompt = {
  ...crossing,
  id: 9,
  kind: 'stake_outcome',
  kind_label: 'Stake outcome',
  scene: null,
  character_sheet: null,
  subject_name: '',
  subject_persona_id: null,
  stake_summary: 'The bridge holds.',
  room_text: 'The bridge groans but holds.',
  private_text: '',
  prepared_for_character: false,
};

describe('NarrationComposer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ties the composer to the event', () => {
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    expect(screen.getByText(/Tied to/)).toBeInTheDocument();
    expect(screen.getByText(/Crossing: Rowan Ashcombe/)).toBeInTheDocument();
    expect(screen.getByText('Prepared for this character')).toBeInTheDocument();
  });

  // Demo-fidelity fix round (F5): "Tied to" is its own labelled chip line
  // (not folded into the dialog title), and the dialog still carries an
  // accessible name via DialogTitle.
  it('renders "Tied to" as a labelled chip, separate from the (accessible) dialog title', () => {
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    expect(screen.getByRole('dialog', { name: 'Narrate Crossing' })).toBeInTheDocument();
    const label = screen.getByText('Tied to');
    expect(label.tagName).toBe('P');
    expect(screen.getByText('Crossing: Rowan Ashcombe').tagName).toBe('SPAN');
  });

  it('renders the Audience line as static labels, not a toggle (R10-1)', () => {
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    expect(screen.getByText('Everyone present')).toBeInTheDocument();
    expect(screen.getByText(/Chosen people/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Everyone present' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Chosen people/ })).toBeNull();
  });

  it('sends the prepared text as is to the chosen people', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        promptId: 7,
        text: 'vision',
        audience: 'chosen',
        receiver_persona_ids: [30],
      })
    );
  });

  it('sends the room line to everyone present', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send to the room' }));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ promptId: 7, text: 'room', audience: 'room' })
    );
  });

  it('keeps the draft when a send fails', async () => {
    mutateAsync.mockRejectedValueOnce(new Error('You need GM trust to send privately.'));
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit before sending' }));
    const box = screen.getByLabelText('Private line');
    fireEvent.change(box, { target: { value: 'my edit' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send privately' }));
    expect(await screen.findByText('You need GM trust to send privately.')).toBeInTheDocument();
    expect(screen.getByLabelText('Private line')).toHaveValue('my edit');
  });

  // Demo-fidelity fix round (F2): a successful private send shows a clear
  // sent state instead of leaving the quote looking blank and the button
  // greyed out, and the GM can still write and send another private line.
  it('shows a sent notice with the sent text after a successful private send, and stays open for another line', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    expect(screen.getByTestId('private-quote')).toHaveTextContent('vision');
    expect(screen.queryByTestId('private-sent-notice')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));

    // The sent notice names who it went to and quotes what was sent.
    const notice = await screen.findByTestId('private-sent-notice');
    expect(notice).toHaveTextContent('Sent to Rowan Ashcombe.');
    expect(notice).toHaveTextContent('vision');
    expect(notice).toHaveAttribute('role', 'status');
    // The old blockquote preview is gone -- a fresh, empty, editable line
    // takes its place so the GM can send another.
    expect(screen.queryByTestId('private-quote')).toBeNull();
    const box = screen.getByLabelText('Private line');
    expect(box).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Send privately' })).toBeInTheDocument();
    // ...and the room line draft is untouched by the private send.
    expect(screen.getByLabelText('Room line')).toHaveValue('room');
  });

  it('shows a sent notice with the sent text after a successful room send, and stays open for another line', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send to the room' }));
    await waitFor(() => expect(screen.getByLabelText('Room line')).toHaveValue(''));

    const notice = await screen.findByTestId('room-sent-notice');
    expect(notice).toHaveTextContent('Sent to the room.');
    expect(notice).toHaveTextContent('room');
    expect(notice).toHaveAttribute('role', 'status');
    expect(screen.getByLabelText('Room line')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Send to the room' })).toBeInTheDocument();
    // The private draft is untouched by the room send.
    expect(screen.getByTestId('private-quote')).toHaveTextContent('vision');
  });

  it('shows the narrate result message after a successful send (#4101 fix round 1)', async () => {
    mutateAsync.mockResolvedValueOnce({
      message: 'That prompt was closed before your line landed; it went out as plain narration.',
    });
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send to the room' }));
    expect(
      await screen.findByText(
        'That prompt was closed before your line landed; it went out as plain narration.'
      )
    ).toBeInTheDocument();
  });

  it('disables each send button while its own draft is empty or whitespace', () => {
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.change(screen.getByLabelText('Room line'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Send to the room' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Edit before sending' }));
    fireEvent.change(screen.getByLabelText('Private line'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Send privately' })).toBeDisabled();
  });

  it('shows a blank private line for a kind with no private_text, and sends it privately', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer
        prompt={stakeOutcome}
        sceneId="1"
        personas={[]}
        open
        onOpenChange={() => {}}
      />
    );
    expect(screen.queryByText('Prepared for this character')).toBeNull();
    expect(screen.queryByText('Authored text')).toBeNull();
    const box = screen.getByLabelText('Private line');
    expect(box).toHaveValue('');
    const sendButton = screen.getByRole('button', { name: 'Send privately' });
    expect(sendButton).toBeDisabled();
    fireEvent.change(box, { target: { value: 'A private word for them.' } });
    expect(sendButton).not.toBeDisabled();
    fireEvent.click(sendButton);
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        promptId: 9,
        text: 'A private word for them.',
        audience: 'chosen',
        receiver_persona_ids: [],
      })
    );
  });
});
