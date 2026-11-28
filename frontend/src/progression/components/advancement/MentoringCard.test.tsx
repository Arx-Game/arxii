/**
 * MentoringCard tests (#5326). Mocks `@/skills/queries` like TrainingCard.test.tsx.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MentoringCard } from './MentoringCard';
import type { useAnswerMentoringMutation, useMentoringQuery } from '@/skills/queries';
import type { MentoringList } from '@/skills/types';

vi.mock('@/skills/queries', () => ({
  useMentoringQuery: vi.fn(),
  useAnswerMentoringMutation: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import * as skillsQueries from '@/skills/queries';

const request = {
  allocation_id: 11,
  student_name: 'Wren Alder',
  student_pronoun: 'her',
  mentor_name: 'Drusa Kell',
  skill_name: 'Villainy',
};
const student = {
  allocation_id: 12,
  student_name: 'Odalys Fenn',
  student_pronoun: 'them',
  mentor_name: 'Magister Vey',
  skill_name: 'Occult',
};

function setupMocks(list: MentoringList) {
  const mutate = vi.fn();
  vi.mocked(skillsQueries.useMentoringQuery).mockReturnValue({
    data: list,
  } as unknown as ReturnType<typeof useMentoringQuery>);
  vi.mocked(skillsQueries.useAnswerMentoringMutation).mockReturnValue({
    mutate,
    isPending: false,
    variables: undefined,
  } as unknown as ReturnType<typeof useAnswerMentoringMutation>);
  return { mutate };
}

describe('MentoringCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the account has no request and no student', () => {
    setupMocks({ requests: [], students: [] });
    renderWithProviders(<MentoringCard />);
    expect(screen.queryByTestId('mentoring-card')).not.toBeInTheDocument();
  });

  it('names who asked which of her characters, with Accept and Decline', () => {
    setupMocks({ requests: [request], students: [] });
    renderWithProviders(<MentoringCard />);
    expect(screen.getByTestId('mentoring-request-row')).toHaveTextContent(
      'Wren Alder asks Drusa Kell to teach her Villainy'
    );
    expect(screen.getByText('Asked to teach')).toBeInTheDocument();
    expect(screen.getByTestId('mentoring-accept-11')).toBeInTheDocument();
    expect(screen.getByTestId('mentoring-decline-11')).toBeInTheDocument();
  });

  it("Accept posts the answer and shows the server's sentence", async () => {
    const { mutate } = setupMocks({ requests: [request], students: [] });
    mutate.mockImplementation(
      (_vars: unknown, opts: { onSuccess: (result: { detail: string }) => void }) =>
        opts.onSuccess({ detail: 'You agree to teach Wren Alder Villainy.' })
    );
    renderWithProviders(<MentoringCard />);

    await userEvent.click(screen.getByTestId('mentoring-accept-11'));

    expect(mutate).toHaveBeenCalledWith({ allocationId: 11, answer: 'accept' }, expect.anything());
    expect(toast.success).toHaveBeenCalledWith('You agree to teach Wren Alder Villainy.');
  });

  it("a refused Accept shows the server's sentence and keeps the row", async () => {
    const { mutate } = setupMocks({ requests: [request], students: [] });
    mutate.mockImplementation((_vars: unknown, opts: { onError: (e: unknown) => void }) =>
      opts.onError(new Error('Your Tradition does not teach Villainy.'))
    );
    renderWithProviders(<MentoringCard />);

    await userEvent.click(screen.getByTestId('mentoring-accept-11'));

    expect(toast.error).toHaveBeenCalledWith('Your Tradition does not teach Villainy.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId('mentoring-request-row')).toBeInTheDocument();
    expect(screen.getByTestId('mentoring-decline-11')).toBeEnabled();
  });

  it('Decline posts the decline answer', async () => {
    const { mutate } = setupMocks({ requests: [request], students: [] });
    renderWithProviders(<MentoringCard />);

    await userEvent.click(screen.getByTestId('mentoring-decline-11'));

    expect(mutate).toHaveBeenCalledWith({ allocationId: 11, answer: 'decline' }, expect.anything());
  });

  it('lists each student she teaches and Stop ends it', async () => {
    const { mutate } = setupMocks({ requests: [], students: [student] });
    renderWithProviders(<MentoringCard />);

    expect(screen.getByText('Teaching')).toBeInTheDocument();
    expect(screen.getByTestId('mentoring-student-row')).toHaveTextContent(
      'Magister Vey teaches Odalys Fenn Occult'
    );

    await userEvent.click(screen.getByTestId('mentoring-stop-12'));

    expect(mutate).toHaveBeenCalledWith({ allocationId: 12, answer: 'stop' }, expect.anything());
  });

  it('disables the buttons of a row while its answer is in flight', () => {
    const { mutate } = setupMocks({ requests: [request], students: [] });
    vi.mocked(skillsQueries.useAnswerMentoringMutation).mockReturnValue({
      mutate,
      isPending: true,
      variables: { allocationId: 11, answer: 'accept' },
    } as unknown as ReturnType<typeof useAnswerMentoringMutation>);
    renderWithProviders(<MentoringCard />);

    expect(screen.getByTestId('mentoring-accept-11')).toBeDisabled();
    expect(screen.getByTestId('mentoring-decline-11')).toBeDisabled();
  });
});
