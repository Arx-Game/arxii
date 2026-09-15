import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationSidebar } from './ConversationSidebar';

describe('ConversationSidebar', () => {
  it('states that OOC channels are unavailable, pending #3299', () => {
    render(<ConversationSidebar onThreadClick={vi.fn()} />);
    expect(screen.getByText(/OOC channels unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/#3299/)).toBeInTheDocument();
  });
});
