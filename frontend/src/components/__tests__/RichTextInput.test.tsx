import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { RichTextInput } from '../RichTextInput';

describe('RichTextInput', () => {
  const defaultProps = {
    value: '',
    onChange: vi.fn(),
    onSubmit: vi.fn(),
  };

  it('renders textarea with toolbar buttons', () => {
    render(<RichTextInput {...defaultProps} />);
    expect(screen.getByRole('toolbar')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByTitle('Bold (Ctrl+B)')).toBeInTheDocument();
    expect(screen.getByTitle('Italic (Ctrl+I)')).toBeInTheDocument();
    expect(screen.getByTitle('Strikethrough (Ctrl+Shift+S)')).toBeInTheDocument();
  });

  it('toolbar buttons have correct labels and titles', () => {
    render(<RichTextInput {...defaultProps} />);

    const boldBtn = screen.getByTitle('Bold (Ctrl+B)');
    expect(boldBtn).toHaveTextContent('B');

    const italicBtn = screen.getByTitle('Italic (Ctrl+I)');
    expect(italicBtn).toHaveTextContent('I');

    const strikeBtn = screen.getByTitle('Strikethrough (Ctrl+Shift+S)');
    expect(strikeBtn).toHaveTextContent('S');
  });

  it('textarea has spellCheck enabled', () => {
    render(<RichTextInput {...defaultProps} />);
    const textarea = screen.getByRole('textbox');
    expect(textarea).toHaveAttribute('spellcheck', 'true');
  });

  it('renders a color picker trigger', () => {
    render(<RichTextInput {...defaultProps} />);
    expect(screen.getByTitle('Text Color')).toBeInTheDocument();
  });

  it('calls onSubmit when Enter pressed (not Shift+Enter)', () => {
    const onSubmit = vi.fn();
    render(<RichTextInput {...defaultProps} onSubmit={onSubmit} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('does not call onSubmit when Shift+Enter pressed', () => {
    const onSubmit = vi.fn();
    render(<RichTextInput {...defaultProps} onSubmit={onSubmit} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('calls onChange when text is typed', async () => {
    const onChange = vi.fn();
    render(<RichTextInput {...defaultProps} onChange={onChange} />);
    const textarea = screen.getByRole('textbox');

    await userEvent.type(textarea, 'hello');
    expect(onChange).toHaveBeenCalled();
  });

  it('passes through onKeyDown to parent handler', () => {
    const onKeyDown = vi.fn();
    render(<RichTextInput {...defaultProps} onKeyDown={onKeyDown} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'ArrowUp' });
    expect(onKeyDown).toHaveBeenCalledTimes(1);
  });

  it('does not pass through formatting shortcuts to parent', () => {
    const onKeyDown = vi.fn();
    render(<RichTextInput {...defaultProps} onKeyDown={onKeyDown} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'b', ctrlKey: true });
    expect(onKeyDown).not.toHaveBeenCalled();
  });

  it('applies custom className', () => {
    const { container } = render(<RichTextInput {...defaultProps} className="my-custom-class" />);
    expect(container.firstChild).toHaveClass('my-custom-class');
  });

  it('renders with custom placeholder', () => {
    render(<RichTextInput {...defaultProps} placeholder="Type here..." />);
    expect(screen.getByPlaceholderText('Type here...')).toBeInTheDocument();
  });

  it('renders mode label pill when modeLabel is provided', () => {
    render(<RichTextInput {...defaultProps} modeLabel="Pose → Room" />);
    expect(screen.getByText('Pose → Room')).toBeInTheDocument();
  });

  it('does not render mode label when modeLabel is not provided', () => {
    render(<RichTextInput {...defaultProps} />);
    expect(screen.queryByText('Pose → Room')).not.toBeInTheDocument();
  });
});
