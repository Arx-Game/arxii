import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { GMPrompt } from '../../types';

vi.mock('../../gmPromptQueries', async (orig) => ({
  ...(await orig<typeof import('../../gmPromptQueries')>()),
  useGMPrompts: vi.fn(),
}));

import { GMPromptQueue } from '../GMPromptQueue';
import { useGMPrompts } from '../../gmPromptQueries';

const mockUseGMPrompts = vi.mocked(useGMPrompts);

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
const moment: GMPrompt = {
  ...crossing,
  id: 8,
  kind: 'dramatic_moment',
  kind_label: 'Dramatic Moment',
  subject_name: 'Tamsin Vale',
  moment_type_label: 'stand against the collapse',
};

describe('GMPromptQueue', () => {
  beforeEach(() => {
    mockUseGMPrompts.mockReturnValue({
      data: [crossing, moment],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
  });

  it('lists every prompt kind in one queue', () => {
    renderWithProviders(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(screen.getByText('GM prompts')).toBeInTheDocument();
    // A narration row's ruled text already carries the kind, so no separate
    // chip repeats it (ruling R14-2, F3); a dramatic moment's body never
    // mentions its kind, so its chip stays.
    expect(screen.getByText(/Crossing: Rowan Ashcombe/)).toBeInTheDocument();
    expect(screen.getByText('Dramatic Moment')).toBeInTheDocument();
  });

  it('offers Open on narration prompts and Confirm on dramatic moments', () => {
    renderWithProviders(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(screen.getByRole('button', { name: /open crossing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm dramatic moment/i })).toBeInTheDocument();
  });
});

describe('GMPromptQueue — empty queue', () => {
  it('renders nothing with an empty queue', () => {
    mockUseGMPrompts.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
    const { container } = render(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('GMPromptQueue — final review (#4101)', () => {
  it('keeps the open composer mounted when the queue empties (F3)', async () => {
    const user = userEvent.setup();
    mockUseGMPrompts.mockReturnValue({
      data: [crossing],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
    const queryClient = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { rerender } = render(<GMPromptQueue sceneId="1" personas={[]} />, { wrapper });
    await user.click(screen.getByRole('button', { name: /open crossing/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    mockUseGMPrompts.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
    rerender(<GMPromptQueue sceneId="1" personas={[]} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByTestId('gm-prompt-row')).toBeNull();
  });

  it('says so when the queue fails to load (F6)', () => {
    mockUseGMPrompts.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Failed to load GM prompts'),
    } as unknown as ReturnType<typeof useGMPrompts>);
    renderWithProviders(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load GM prompts');
  });
});
