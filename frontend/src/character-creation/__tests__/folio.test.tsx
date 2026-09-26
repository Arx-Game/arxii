import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { codexKeys } from '@/codex/queries';
import {
  ChapterLeaf,
  CodexLine,
  Entry,
  EntryDoors,
  EntryList,
  InstrumentFrame,
  InstrumentGroup,
  Paragraphs,
  RecordRail,
  StatRow,
} from '../folio';
import { ChoiceRow } from '../folio/ChoiceRow';
import { Field } from '../folio/Field';
import { Stage } from '../types';
import { mockCodexEntry } from './fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from './testUtils';

describe('ChapterLeaf', () => {
  it('opens with the eyebrow and one h1 and puts the aside in a marginalia landmark', () => {
    render(
      <ChapterLeaf stage={Stage.ORIGIN} title="Where does the story begin?" aside={<p>note</p>}>
        <p>body</p>
      </ChapterLeaf>
    );
    expect(screen.getByText('Stage 1 of 10')).toHaveClass('chapter-no');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('complementary', { name: /marginalia/i })).toHaveTextContent('note');
  });
});

describe('RecordRail', () => {
  it('lists chosen values and marks the unchosen as unwritten', () => {
    render(
      <RecordRail
        rows={[{ label: 'Origin', value: 'Perdition' }, { label: 'Species' }]}
        ledger="One of eleven chapters begun."
      />
    );
    expect(screen.getByRole('heading', { name: /your choices so far/i })).toBeInTheDocument();
    expect(screen.getByText('Perdition')).toBeInTheDocument();
    expect(screen.getByText('not yet chosen')).toHaveClass('unwritten');
    expect(screen.getByText('One of eleven chapters begun.')).toHaveClass('rail-ledger');
  });
});

describe('Entry', () => {
  it('offers a Select mark in the name row that chooses without opening the entry (#4022)', async () => {
    const onChoose = vi.fn();
    render(
      <EntryList label="Starting realms">
        <Entry
          name="Perdition"
          tag="The Grand Principality of Inferna"
          chosen={false}
          onChoose={onChoose}
          onSetAside={vi.fn()}
        >
          <p>prose</p>
          <EntryDoors
            chooseLabel="Select Perdition"
            onChoose={onChoose}
            chosen={false}
            onSetAside={vi.fn()}
          />
        </Entry>
      </EntryList>
    );
    const summary = screen.getByText('Perdition').closest('summary')!;
    const mark = within(summary).getByRole('button', { name: 'Select Perdition' });
    expect(mark).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(mark);
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(summary.closest('details')).not.toHaveAttribute('open');
    // The foot keeps one door to select from the end of the reading.
    const doors = screen.getAllByRole('button', { name: 'Select Perdition', hidden: true });
    await userEvent.click(doors.find((door) => !summary.contains(door))!);
    expect(onChoose).toHaveBeenCalledTimes(2);
  });

  it('reads Selected on the mark when chosen, tints the row, and clears on a second press (#4022)', async () => {
    const onSetAside = vi.fn();
    render(
      <EntryList label="Starting realms">
        <Entry
          name="Perdition"
          tag="The Grand Principality of Inferna"
          chosen
          open
          onChoose={vi.fn()}
          onSetAside={onSetAside}
        >
          <p>prose</p>
          <EntryDoors
            chooseLabel="Select Perdition"
            onChoose={vi.fn()}
            chosen
            onSetAside={onSetAside}
          />
        </Entry>
      </EntryList>
    );
    const summary = screen.getByText('Perdition').closest('summary')!;
    const mark = within(summary).getByRole('button', { name: 'Selected Perdition' });
    expect(mark).toHaveAttribute('aria-pressed', 'true');
    expect(summary.closest('li')).toHaveClass('chosen');
    expect(screen.queryByText('Selected.')).not.toBeInTheDocument();
    await userEvent.click(mark);
    expect(onSetAside).toHaveBeenCalledTimes(1);
    // The foot door now reads Clear.
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(onSetAside).toHaveBeenCalledTimes(2);
  });

  it('keeps a non-clearing mark when the choice cannot be set aside (#4022)', () => {
    render(
      <EntryList label="Traditions">
        <Entry name="The Hollow Choir" tag="Available" chosen open onChoose={vi.fn()}>
          <p>prose</p>
          <EntryDoors chooseLabel="Select The Hollow Choir" onChoose={vi.fn()} chosen />
        </Entry>
      </EntryList>
    );
    const summary = screen.getByText('The Hollow Choir').closest('summary')!;
    expect(
      within(summary).getByRole('button', { name: 'Selected The Hollow Choir' })
    ).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
  });
});

describe('StatRow', () => {
  it('labels the output, disables at the cap with a reason, and announces nothing itself', () => {
    render(
      <InstrumentFrame
        label="Statistics"
        ledger={{
          left: 'Twelve statistics',
          right: (
            <>
              Points remaining: <b>0</b>
            </>
          ),
        }}
      >
        <InstrumentGroup title="Physical" gloss="the body">
          <StatRow
            id="lbl-strength"
            name="strength"
            value={6}
            max={6}
            onChange={vi.fn()}
            canDecrease
            canIncrease={false}
            increaseTitle="At 6, the most it can be"
          />
        </InstrumentGroup>
      </InstrumentFrame>
    );
    expect(screen.getByRole('status', { hidden: true })).toHaveTextContent('6');
    const plus = screen.getByRole('button', { name: /raise strength/i });
    expect(plus).toBeDisabled();
    expect(plus).toHaveAttribute('title', 'At 6, the most it can be');
  });
});

describe('ChoiceRow', () => {
  it('presses the chosen option and reports a change', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ChoiceRow
        label="Gender"
        options={[
          { value: 1, label: 'Male' },
          { value: 2, label: 'Female' },
        ]}
        value={1}
        onChange={onChange}
      />
    );
    expect(screen.getByRole('group', { name: 'Gender' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Male' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Female' }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('clears only when clearable', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(
      <ChoiceRow
        label="Build"
        options={[{ value: 'a', label: 'A' }]}
        value="a"
        onChange={onChange}
      />
    );
    await user.click(screen.getByRole('button', { name: 'A' }));
    expect(onChange).not.toHaveBeenCalled();
    rerender(
      <ChoiceRow
        label="Build"
        options={[{ value: 'a', label: 'A' }]}
        value="a"
        onChange={onChange}
        clearable
      />
    );
    await user.click(screen.getByRole('button', { name: 'A' }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});

describe('Field', () => {
  it('labels its control and shows the hint', () => {
    render(
      <Field id="f" label="Concept" hint="One line.">
        <input id="f" type="text" />
      </Field>
    );
    expect(screen.getByLabelText('Concept')).toBeInTheDocument();
    expect(screen.getByText('One line.')).toHaveClass('hint');
  });
});

describe('Entry lead', () => {
  it('renders the lead before the name, hidden from assistive tech', () => {
    render(
      <EntryList label="Paths">
        <Entry name="Blade" tag="Valor" chosen={false} lead={<i data-testid="ico" />}>
          <p>prose</p>
        </Entry>
      </EntryList>
    );
    expect(screen.getByTestId('ico').parentElement).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('Paragraphs', () => {
  it('splits blank-line-separated text into separate paragraphs', () => {
    render(<Paragraphs text={'First paragraph.\n\nSecond paragraph.'} />);
    expect(screen.getByText('First paragraph.').tagName).toBe('P');
    expect(screen.getByText('Second paragraph.').tagName).toBe('P');
  });
});

describe('CodexLine', () => {
  it('renders the codex line for an entry id and nothing at all without one', () => {
    const queryClient = createTestQueryClient();
    // CodexTerm mounts CodexModal, which fetches its entry on mount rather
    // than on open — seed it so the test never reaches the real codex API.
    seedQueryData(queryClient, codexKeys.entry(7), mockCodexEntry(7));

    const { rerender, container } = renderWithCharacterCreationProviders(
      <CodexLine entryId={7} name="Duskborn Rite" />,
      { queryClient }
    );
    expect(screen.getByRole('button', { name: 'Codex: Duskborn Rite' }).closest('p')).toHaveClass(
      'ledger-line'
    );

    rerender(<CodexLine entryId={null} name="Duskborn Rite" />);
    expect(container).toBeEmptyDOMElement();
  });
});
