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

describe('NarrationComposer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ties the composer to the event', () => {
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    expect(screen.getByText(/Crossing: Rowan Ashcombe/)).toBeInTheDocument();
    expect(screen.getByText('Prepared for this character')).toBeInTheDocument();
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

  it('clears only the private draft after a successful private send', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    // The room line draft is untouched by the private send.
    expect(screen.getByLabelText('Room line')).toHaveValue('room');
  });

  it('clears only the room draft after a successful room send', async () => {
    mutateAsync.mockResolvedValueOnce({});
    renderWithProviders(
      <NarrationComposer prompt={crossing} sceneId="1" personas={[]} open onOpenChange={() => {}} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send to the room' }));
    await waitFor(() => expect(screen.getByLabelText('Room line')).toHaveValue(''));
  });
});
