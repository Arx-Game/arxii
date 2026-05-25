import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PersonaAvatar } from '../PersonaAvatar';

describe('PersonaAvatar', () => {
  it('renders the persona thumbnail when thumbnailMediaUrl is set', () => {
    render(<PersonaAvatar source={{ name: 'Aerande', thumbnailMediaUrl: '/media/x.png' }} />);
    expect(screen.getByRole('img')).toHaveAttribute('src', '/media/x.png');
  });

  it('falls back to thumbnailUrl when thumbnailMediaUrl is absent', () => {
    render(<PersonaAvatar source={{ name: 'Aerande', thumbnailUrl: 'https://x/y.png' }} />);
    expect(screen.getByRole('img')).toHaveAttribute('src', 'https://x/y.png');
  });

  it('renders initial-letter avatar when no images set', () => {
    render(<PersonaAvatar source={{ name: 'Aerande' }} />);
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('uses deterministic color across re-renders for the same name', () => {
    const { rerender } = render(<PersonaAvatar source={{ name: 'Aerande' }} />);
    const first = screen.getByText('A').getAttribute('style');
    rerender(<PersonaAvatar source={{ name: 'Aerande' }} />);
    expect(screen.getByText('A').getAttribute('style')).toBe(first);
  });
});
