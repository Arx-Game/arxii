import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActionResult } from './ActionResult';

describe('ActionResult', () => {
  it('renders action name from parsed content', () => {
    render(
      <ActionResult content="[Intimidate] using Menacing Glare -- Critical Success (Major)" />
    );

    expect(screen.getByText('Intimidate')).toBeInTheDocument();
  });

  it('renders technique name from parsed content', () => {
    render(
      <ActionResult content="[Intimidate] using Menacing Glare -- Critical Success (Major)" />
    );

    expect(screen.getByText(/using Menacing Glare/)).toBeInTheDocument();
  });

  it('renders outcome from parsed content', () => {
    render(
      <ActionResult content="[Intimidate] using Menacing Glare -- Critical Success (Major)" />
    );

    expect(screen.getByText('Critical Success')).toBeInTheDocument();
    expect(screen.getByText('(Major)')).toBeInTheDocument();
  });

  it('renders with success styling (green border) for success outcomes', () => {
    const { container } = render(<ActionResult content="[Perform] -- Success" outcome="Success" />);

    const resultDiv = container.firstElementChild as HTMLElement;
    expect(resultDiv.className).toContain('border-l-green-500');
  });

  it('renders with failure styling (red border) for failure outcomes', () => {
    const { container } = render(<ActionResult content="[Perform] -- Failure" outcome="Failure" />);

    const resultDiv = container.firstElementChild as HTMLElement;
    expect(resultDiv.className).toContain('border-l-red-500');
  });

  it('renders with yellow border for mixed outcomes', () => {
    const { container } = render(
      <ActionResult content="[Perform] -- Mixed Result" outcome="Mixed Result" />
    );

    const resultDiv = container.firstElementChild as HTMLElement;
    expect(resultDiv.className).toContain('border-l-yellow-500');
  });

  it('renders with blue border when no outcome provided', () => {
    const { container } = render(<ActionResult content="[Perform]" />);

    const resultDiv = container.firstElementChild as HTMLElement;
    expect(resultDiv.className).toContain('border-l-blue-500');
  });

  it('uses explicit actionKey prop over parsed content', () => {
    render(<ActionResult content="[Perform]" actionKey="Custom Action" />);

    expect(screen.getByText('Custom Action')).toBeInTheDocument();
  });

  it('uses explicit techniqueName prop over parsed content', () => {
    render(
      <ActionResult content="[Perform] using Parsed Technique" techniqueName="Override Technique" />
    );

    expect(screen.getByText(/using Override Technique/)).toBeInTheDocument();
  });

  it('shows "Show details" button that expands mechanical info', async () => {
    const user = userEvent.setup();
    const rawContent = '[Intimidate] using Menacing Glare -- Critical Success (Major)';

    render(<ActionResult content={rawContent} />);

    // Initially collapsed
    expect(screen.getByText('Show details')).toBeInTheDocument();
    expect(screen.queryByText('Hide details')).not.toBeInTheDocument();

    // Click to expand
    await user.click(screen.getByText('Show details'));

    // Now shows the raw content and the hide button
    expect(screen.getByText('Hide details')).toBeInTheDocument();
    // The raw content appears in the expanded details section (as monospace text)
    const monoElement = screen.getByText(rawContent, { selector: '.font-mono' });
    expect(monoElement).toBeInTheDocument();
  });

  it('hides details when clicking "Hide details"', async () => {
    const user = userEvent.setup();
    const rawContent = '[Perform] -- Success';

    render(<ActionResult content={rawContent} />);

    // Expand
    await user.click(screen.getByText('Show details'));
    expect(screen.getByText('Hide details')).toBeInTheDocument();

    // Collapse
    await user.click(screen.getByText('Hide details'));
    expect(screen.getByText('Show details')).toBeInTheDocument();
  });

  it('falls back to "Action" when content cannot be parsed', () => {
    render(<ActionResult content="some unparseable text" />);

    expect(screen.getByText('Action')).toBeInTheDocument();
    // Shows raw content since it could not be parsed
    expect(screen.getByText('some unparseable text')).toBeInTheDocument();
  });
});
