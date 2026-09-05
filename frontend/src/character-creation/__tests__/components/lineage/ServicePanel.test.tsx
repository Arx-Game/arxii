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
  it('excludes the draft own family org, shows other staff houses grouped by organization, and hides kin rows', async () => {
    const elsewhereRetainer = {
      ...mockVacancyRetainer,
      id: 803,
      name: 'Steward',
      organization: {
        id: 902,
        name: 'House Elsewhere',
        family: { id: 7, name: 'Elsewhere', influence: 3 },
      },
    };
    vi.mocked(api.getVacancies).mockResolvedValue([
      mockVacancyRetainer,
      elsewhereRetainer,
      mockVacancyKin,
    ]);

    renderWithCharacterCreationProviders(
      <ServicePanel draft={mockDraftWithFamily} heading="Service" />
    );

    expect(await screen.findByText(elsewhereRetainer.name)).toBeInTheDocument();
    expect(screen.getByText(elsewhereRetainer.organization.name)).toBeInTheDocument();
    // mockVacancyRetainer's organization.family.id (1) matches the draft's own
    // family (mockNobleFamily.id, 1), so it must be excluded, not rendered.
    expect(screen.queryByText(mockVacancyRetainer.name)).not.toBeInTheDocument();
    // Kin-basis rows never belong in the Service panel.
    expect(screen.queryByText(mockVacancyKin.name)).not.toBeInTheDocument();
  });
});
