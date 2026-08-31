import { screen, within } from '@testing-library/react';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PreviewDialog } from '../PreviewDialog';

function renderDialog(overrides: Partial<Parameters<typeof PreviewDialog>[0]> = {}) {
  renderWithProviders(
    <PreviewDialog
      open
      onOpenChange={vi.fn()}
      name="The Grand Foyer"
      description="A hall meant to impress."
      locationPath={['Arx', 'Central Ward']}
      exitNames={['north', 'south']}
      artUrl={null}
      {...overrides}
    />
  );
}

describe('PreviewDialog', () => {
  it('renders the live (unsaved) name/description on the web card', () => {
    renderDialog();
    const card = screen.getByTestId('preview-web-card');
    expect(within(card).getByText('The Grand Foyer')).toBeInTheDocument();
    expect(within(card).getByText('A hall meant to impress.')).toBeInTheDocument();
    expect(within(card).getByText('north, south', { exact: false })).toBeInTheDocument();
  });

  it('renders the same real payload in the telnet-style scroll', () => {
    renderDialog();
    const telnet = screen.getByTestId('preview-telnet');
    expect(telnet).toHaveTextContent('The Grand Foyer');
    expect(telnet).toHaveTextContent('A hall meant to impress.');
    expect(telnet).toHaveTextContent('Exits: north, south.');
  });

  it('never fabricates content that has no backing data — no invented occupancy line', () => {
    renderDialog();
    expect(screen.queryByText(/is here/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/GM/)).not.toBeInTheDocument();
  });

  it('shows honest placeholders for an empty description and no exits', () => {
    renderDialog({ description: '', exitNames: [] });
    const card = screen.getByTestId('preview-web-card');
    expect(within(card).getByText('(no description yet)')).toBeInTheDocument();
    expect(card).toHaveTextContent('Exits: none');
  });

  it('shows the art image only when artUrl is present', () => {
    renderDialog({ artUrl: 'https://example.test/art.png' });
    expect(screen.getByTestId('preview-art')).toHaveAttribute(
      'src',
      'https://example.test/art.png'
    );
  });
});
