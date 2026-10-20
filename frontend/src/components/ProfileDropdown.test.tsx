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

  it('links the Almanach and the World Builder for staff users (#4518)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockStaffAccount} />);

    await user.click(screen.getByText(mockStaffAccount.display_name));

    expect(screen.getByText('Almanach').closest('a')).toHaveAttribute('href', '/staff/almanach');
    expect(screen.getByText('World Builder').closest('a')).toHaveAttribute(
      'href',
      '/staff/world-builder'
    );
  });

  it('does not show the Almanach for non-staff users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.queryByText('Almanach')).not.toBeInTheDocument();
  });

  it('shows Profile link for all users', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.getByText('Profile')).toBeInTheDocument();
  });

  it('shows Log Out Account for all users (#4321: the account, not the character)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfileDropdown account={mockAccount} />);

    await user.click(screen.getByText(mockAccount.display_name));

    expect(screen.getByText('Log Out Account')).toBeInTheDocument();
    expect(screen.queryByText('Logout')).not.toBeInTheDocument();
  });
});
