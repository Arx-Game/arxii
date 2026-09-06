import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { VacancyPicker } from '../../../components/lineage/VacancyPicker';
import { mockDraftWithFamily, mockVacancyKin, mockVacancyRetainer } from '../../fixtures';

describe('VacancyPicker', () => {
  it('shows importance, presumed importance, price and standing capacity', () => {
    render(
      <VacancyPicker
        draft={mockDraftWithFamily}
        vacancies={[mockVacancyKin, mockVacancyRetainer]}
        onPick={vi.fn()}
      />
    );
    expect(screen.getByText(mockVacancyKin.name)).toBeInTheDocument();
    expect(screen.getByText(/importance 1/i)).toBeInTheDocument();
    expect(screen.getByText(/presumed 5/i)).toBeInTheDocument();
    expect(screen.getByText(/6 pts/)).toBeInTheDocument();
    expect(screen.getByText(/standing/i)).toBeInTheDocument();
  });

  it('picks and unpicks', async () => {
    const onPick = vi.fn();
    render(
      <VacancyPicker
        draft={{ ...mockDraftWithFamily, selected_vacancy: mockVacancyKin.id }}
        vacancies={[mockVacancyKin]}
        onPick={onPick}
      />
    );
    const card = screen.getByRole('button', { name: new RegExp(mockVacancyKin.name) });
    expect(card).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(card);
    expect(onPick).toHaveBeenCalledWith(null);
  });
});
