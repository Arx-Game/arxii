import { screen } from '@testing-library/react';
import { NotFoundPage } from './NotFoundPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

describe('NotFoundPage', () => {
  it('renders not found message', () => {
    renderWithProviders(<NotFoundPage />);
    expect(screen.getByRole('heading', { name: /404 - Page Not Found/i })).toBeInTheDocument();
  });
});
