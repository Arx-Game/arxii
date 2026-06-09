import { render, screen } from '@testing-library/react';
import { PowerLedgerPanel } from './PowerLedgerPanel';

const ledger = {
  entries: [
    { stage: 'base', source_label: 'channeled intensity', op: 'set', amount: 5, running_total: 5 },
    {
      stage: 'penetration',
      source_label: 'ward (penetrated)',
      op: 'set',
      amount: 12,
      running_total: 12,
    },
  ],
  total: 12,
};

describe('PowerLedgerPanel', () => {
  it('renders nothing for null', () => {
    const { container } = render(<PowerLedgerPanel ledger={null} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('renders rows + total', () => {
    render(<PowerLedgerPanel ledger={ledger} />);
    expect(screen.getByText('Channeled intensity')).toBeInTheDocument();
    expect(screen.getByTestId('power-ledger-total')).toHaveTextContent('12');
  });
  it('emphasizes a penetration entry', () => {
    render(<PowerLedgerPanel ledger={ledger} />);
    expect(screen.getByTestId('power-ledger-row-penetration')).toBeInTheDocument();
  });
});
