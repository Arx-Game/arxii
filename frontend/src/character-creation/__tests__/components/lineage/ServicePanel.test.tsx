import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { ServicePanel } from '../../../components/lineage/ServicePanel';
import * as api from '../../../api';
import { mockDraftWithFamily, mockVacancyKin, mockVacancyRetainer } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

vi.mock('../../../api', () => ({
  getVacancies: vi.fn(),
}));

describe('ServicePanel', () => {
  it('shows only retainer vacancies at other staff houses, grouped by organization', async () => {
    vi.mocked(api.getVacancies).mockResolvedValue([mockVacancyRetainer, mockVacancyKin]);
    const draft = { ...mockDraftWithFamily, family: null };

    renderWithCharacterCreationProviders(<ServicePanel draft={draft} heading="Service" />);

    expect(await screen.findByText(mockVacancyRetainer.name)).toBeInTheDocument();
    expect(screen.queryByText(mockVacancyKin.name)).not.toBeInTheDocument();
    expect(screen.getByText(mockVacancyRetainer.organization.name)).toBeInTheDocument();
  });
});
