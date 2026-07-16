/**
 * Tests for ContentSections inline link rendering.
 *
 * Verifies that [[wikilink]] syntax is parsed and rendered as either
 * clickable links (accessible) or "???" (inaccessible).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoreSection, OOCSection } from '../components/ContentSections';
import type { CodexLinkRef } from '../types';

describe('LoreSection', () => {
  it('renders plain text without links', () => {
    render(<LoreSection content="Just plain text." />);
    expect(screen.getByText('Just plain text.')).toBeInTheDocument();
  });

  it('renders accessible link as clickable', async () => {
    const links: CodexLinkRef[] = [
      {
        match_text: '[[Linked Entry]]',
        entry_id: 42,
        display_text: 'Linked Entry',
        accessible: true,
      },
    ];
    const onNavigate = vi.fn();
    render(
      <LoreSection
        content="See [[Linked Entry]] for details."
        links={links}
        onNavigate={onNavigate}
      />
    );

    const link = screen.getByText('Linked Entry');
    expect(link.tagName).toBe('BUTTON');
    await userEvent.click(link);
    expect(onNavigate).toHaveBeenCalledWith(42);
  });

  it('renders inaccessible link as ???', () => {
    const links: CodexLinkRef[] = [
      {
        match_text: '[[Secret Entry]]',
        entry_id: null,
        display_text: '???',
        accessible: false,
      },
    ];
    render(<LoreSection content="See [[Secret Entry]] if you dare." links={links} />);

    expect(screen.getByText('???')).toBeInTheDocument();
    // The real entry name should not appear
    expect(screen.queryByText('Secret Entry')).not.toBeInTheDocument();
  });

  it('renders multiple links in sequence', async () => {
    const links: CodexLinkRef[] = [
      {
        match_text: '[[First]]',
        entry_id: 1,
        display_text: 'First',
        accessible: true,
      },
      {
        match_text: '[[Second]]',
        entry_id: 2,
        display_text: 'Second',
        accessible: true,
      },
    ];
    const onNavigate = vi.fn();
    render(
      <LoreSection content="[[First]] then [[Second]]." links={links} onNavigate={onNavigate} />
    );

    await userEvent.click(screen.getByText('First'));
    await userEvent.click(screen.getByText('Second'));
    expect(onNavigate).toHaveBeenNthCalledWith(1, 1);
    expect(onNavigate).toHaveBeenNthCalledWith(2, 2);
  });

  it('renders mixed accessible and inaccessible links', () => {
    const links: CodexLinkRef[] = [
      {
        match_text: '[[Public]]',
        entry_id: 1,
        display_text: 'Public',
        accessible: true,
      },
      {
        match_text: '[[Private]]',
        entry_id: null,
        display_text: '???',
        accessible: false,
      },
    ];
    render(
      <LoreSection content="[[Public]] and [[Private]]." links={links} onNavigate={vi.fn()} />
    );

    expect(screen.getByRole('button', { name: 'Public' })).toBeInTheDocument();
    expect(screen.getByText('???')).toBeInTheDocument();
  });
});

describe('OOCSection', () => {
  it('renders accessible link in OOC content', async () => {
    const links: CodexLinkRef[] = [
      {
        match_text: '[[Mechanics]]',
        entry_id: 10,
        display_text: 'Mechanics',
        accessible: true,
      },
    ];
    const onNavigate = vi.fn();
    render(
      <OOCSection content="See [[Mechanics]] for rules." links={links} onNavigate={onNavigate} />
    );

    await userEvent.click(screen.getByText('Mechanics'));
    expect(onNavigate).toHaveBeenCalledWith(10);
  });
});
