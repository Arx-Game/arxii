import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FormattedContent } from '../FormattedContent';

describe('FormattedContent', () => {
  it('renders plain text', () => {
    render(<FormattedContent content="hello world" />);
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });

  it('renders bold as <strong>', () => {
    render(<FormattedContent content="**bold**" />);
    const el = screen.getByText('bold');
    expect(el.tagName).toBe('STRONG');
  });

  it('renders italic as <em>', () => {
    render(<FormattedContent content="*italic*" />);
    const el = screen.getByText('italic');
    expect(el.tagName).toBe('EM');
  });

  it('renders strikethrough as <del>', () => {
    render(<FormattedContent content="~~struck~~" />);
    const el = screen.getByText('struck');
    expect(el.tagName).toBe('DEL');
  });

  it('renders color with inline style', () => {
    render(<FormattedContent content="|rhello|n" />);
    const el = screen.getByText('hello');
    expect(el.tagName).toBe('SPAN');
    expect(el).toHaveStyle({ color: '#800000' });
  });

  it('renders link as <a> with correct attributes', () => {
    render(<FormattedContent content="visit https://example.com now" />);
    const link = screen.getByText('https://example.com');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('handles empty content', () => {
    const { container } = render(<FormattedContent content="" />);
    expect(container.querySelector('span')).toBeInTheDocument();
    expect(container.querySelector('span')?.children).toHaveLength(0);
  });

  it('applies custom className to wrapper', () => {
    const { container } = render(<FormattedContent content="test" className="custom-class" />);
    expect(container.querySelector('.custom-class')).toBeInTheDocument();
  });

  // #3862: an unbroken run (a URL, a keyboard mash, a long invented word) must
  // break at the column's edge instead of widening the feed sideways. The rule
  // lives on this wrapper, so every reader that renders a body inherits it.
  // jsdom performs no layout, so the assertion is on the mechanism: the
  // `overflow-wrap: anywhere` utility, which (unlike `break-word`) also lets the
  // run shrink a flex child's min-content width, so the column never grows.
  it('wraps an unbroken run of characters at the column edge', () => {
    const unbroken = 'x'.repeat(500);
    const { container } = render(<FormattedContent content={unbroken} />);
    const wrapper = container.querySelector('span');
    expect(wrapper).toHaveClass('[overflow-wrap:anywhere]');
    expect(wrapper).toHaveTextContent(unbroken);
  });

  it('keeps the wrap rule when a custom className is supplied', () => {
    const { container } = render(<FormattedContent content="test" className="custom-class" />);
    const wrapper = container.querySelector('span');
    expect(wrapper).toHaveClass('custom-class');
    expect(wrapper).toHaveClass('[overflow-wrap:anywhere]');
  });
});
