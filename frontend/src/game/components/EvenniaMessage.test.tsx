import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvenniaMessage } from './EvenniaMessage';

describe('EvenniaMessage', () => {
  it('maps Evennia color classes and line breaks', () => {
    render(<EvenniaMessage content='<span class="color-002">Green</span><br>Next line' />);

    const coloredText = screen.getByText('Green');
    expect(coloredText).toHaveClass('text-green-700');
    expect(coloredText.parentElement).toHaveTextContent(/Green\s+Next line/);
  });

  it('sanitizes unsafe markup', () => {
    render(<EvenniaMessage content="<img src=x onerror=alert(1)>Safe<script>alert(1)</script>" />);

    expect(screen.getByText('Safe')).toBeInTheDocument();
    expect(document.querySelector('img')).not.toBeNull();
    expect(document.querySelector('img')).not.toHaveAttribute('onerror');
    expect(document.querySelector('script')).toBeNull();
  });
});
