import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActionResult } from './ActionResult';
import type { ActionResultData } from '../actionTypes';

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

  // ---------------------------------------------------------------------------
  // anima_recovery panel
  // ---------------------------------------------------------------------------

  const baseResult: ActionResultData = {
    interaction_id: 1,
    action_key: 'anima_ritual',
    action_resolution: {
      current_phase: 'resolved',
      main_result: { step_label: 'Roll', check_outcome: 'Success', consequence_id: null },
      gate_results: [],
    },
    technique_result: null,
    technique_name: null,
    check_result: null,
    selected_consequence: null,
    applied_effects: [],
  };

  it('renders anima_recovery panel when present', () => {
    render(
      <ActionResult
        content="[anima_ritual] -- Success"
        result={{
          ...baseResult,
          anima_recovery: { recovered: 3, soulfray_reduced: 2, new_pool: 8 },
        }}
      />
    );

    expect(screen.getByTestId('anima-recovery-panel')).toBeInTheDocument();
    expect(screen.getByText(/recovered 3 anima/i)).toBeInTheDocument();
    expect(screen.getByText(/2 soulfray reduced/i)).toBeInTheDocument();
    expect(screen.getByText(/pool now 8/i)).toBeInTheDocument();
  });

  it('does not render anima_recovery panel when absent', () => {
    render(<ActionResult content="[anima_ritual] -- Success" result={baseResult} />);

    expect(screen.queryByTestId('anima-recovery-panel')).not.toBeInTheDocument();
  });

  it('renders anima_recovery panel without soulfray text when soulfray_reduced is 0', () => {
    render(
      <ActionResult
        content="[anima_ritual] -- Success"
        result={{
          ...baseResult,
          anima_recovery: { recovered: 5, soulfray_reduced: 0, new_pool: 10 },
        }}
      />
    );

    expect(screen.getByTestId('anima-recovery-panel')).toBeInTheDocument();
    expect(screen.getByText(/recovered 5 anima/i)).toBeInTheDocument();
    expect(screen.queryByText(/soulfray reduced/i)).not.toBeInTheDocument();
  });
});
