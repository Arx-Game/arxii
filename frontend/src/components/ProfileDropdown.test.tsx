import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileDropdown } from './ProfileDropdown';
import { mockAccount, mockStaffAccount } from '@/test/mocks/account';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

describe('ProfileDropdown', () => {
  it('does not show Django Admin link for non-staff users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    // Open the dropdown
    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.queryByText('Django Admin')).not.toBeInTheDocument();
  });

  it('shows Django Admin link for staff users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockStaffAccount} />);

    // Open the dropdown
    await user.click(screen.getByText(mockStaffAccount.display_name));

    const adminLink = screen.getByText('Django Admin');
    expect(adminLink).toBeInTheDocument();

    // Verify link attributes
    const linkElement = adminLink.closest('a');
    expect(linkElement).toHaveAttribute('href', '/admin/');
    expect(linkElement).toHaveAttribute('target', '_blank');
    expect(linkElement).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('shows Profile link for all users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.getByText('Profile')).toBeInTheDocument();
  });

  it('shows Logout option for all users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.getByText('Logout')).toBeInTheDocument();
  });
});
