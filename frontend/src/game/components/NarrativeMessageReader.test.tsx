import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NarrativeMessageReader } from './NarrativeMessageReader';
import { GAME_MESSAGE_TYPE } from '@/hooks/types';
import type { GameMessage } from '@/hooks/types';

function makeMessage(content: string): GameMessage & { id: string } {
  return {
    id: '1',
    content,
    timestamp: Date.parse('2026-01-01T00:00:00Z'),
    type: GAME_MESSAGE_TYPE.SYSTEM,
  };
}

describe('NarrativeMessageReader', () => {
  it('renders Evennia color spans and line breaks as formatted content', () => {
    render(
      <NarrativeMessageReader
        messages={[makeMessage('<span class="color-010">Account ready</span><br>Help')]}
      />
    );

    const message = screen.getByText('Account ready');
    expect(message).toHaveClass('text-green-400');
    expect(message.parentElement).toHaveTextContent(/Account ready\s+Help/);
  });

  it('sanitizes unsafe markup while preserving readable message text', () => {
    render(
      <NarrativeMessageReader
        messages={[makeMessage('<img src=x onerror=alert(1)>Welcome<script>alert(1)</script>')]}
      />
    );

    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(document.querySelector('img')).not.toBeNull();
    expect(document.querySelector('img')).not.toHaveAttribute('onerror');
    expect(document.querySelector('script')).toBeNull();
  });
});
