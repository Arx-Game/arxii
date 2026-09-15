import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AttentionBadge } from './AttentionBadge';

describe('AttentionBadge', () => {
  it('shows the direct count', () => {
    render(<AttentionBadge direct={3} ambient={false} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('caps a three digit count at 99+', () => {
    render(<AttentionBadge direct={412} ambient={true} />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('shows exactly 99 uncapped', () => {
    render(<AttentionBadge direct={99} ambient={false} />);
    expect(screen.getByText('99')).toBeInTheDocument();
  });

  it('renders nothing when there is neither', () => {
    const { container } = render(<AttentionBadge direct={0} ambient={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
