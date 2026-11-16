import { createPortal } from 'react-dom';
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
  PageTurn,
  Paragraphs,
  RecordRail,
  StatRow,
  useChapterRail,
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

  // A list the stage builds deep inside itself and sends to the panel's slot (#5148).
  function Choices() {
    const slot = useChapterRail();
    const list = <section aria-label="Life So Far">picks</section>;
    return slot ? createPortal(list, slot) : list;
  }

  it("a railSlot leaf keeps the same panel as every stage and puts the stage's own list under it (#5148)", () => {
    const { container } = render(
      <ChapterLeaf stage={Stage.LINEAGE} title="Lineage" railSlot aside={<p>note</p>}>
        <div data-testid="deep">
          <Choices />
        </div>
      </ChapterLeaf>
    );
    const panel = screen.getByRole('complementary', { name: /marginalia/i });
    const list = screen.getByRole('region', { name: 'Life So Far' });
    expect(panel).toContainElement(list);
    expect(list.parentElement).toHaveClass('rail-slot');
    // The stage's own list comes after what every stage shows.
    expect(panel.firstElementChild).toHaveTextContent('note');
    expect(panel.lastElementChild).toBe(list.parentElement);
    expect(screen.getByTestId('deep')).toBeEmptyDOMElement();
    expect(container.querySelector('.chapter')).toHaveClass('chapter-grids');
    expect(screen.getAllByRole('complementary')).toHaveLength(1);
  });

  it('a leaf that keeps no slot leaves the list where it is written', () => {
    const { container } = render(
      <ChapterLeaf stage={Stage.ORIGIN} title="Origin" aside={<p>note</p>}>
        <div data-testid="deep">
          <Choices />
        </div>
      </ChapterLeaf>
    );
    expect(screen.getByTestId('deep')).toContainElement(
      screen.getByRole('region', { name: 'Life So Far' })
    );
    expect(container.querySelector('.rail-slot')).toBeNull();
    expect(container.querySelector('.chapter')).not.toHaveClass('chapter-grids');
  });
});

describe('PageTurn', () => {
  it('draws the way back as the same button as the way forward (#5146)', () => {
    render(
      <PageTurn
        back={{ label: 'Back: Heritage', onClick: vi.fn() }}
        next={{ label: 'Next: Path', onClick: vi.fn() }}
      />
    );
    const back = screen.getByRole('button', { name: 'Back: Heritage' });
    const next = screen.getByRole('button', { name: 'Next: Path' });
    expect(back.className).toBe(next.className);
    expect(back).toHaveClass('btn');
    expect(back).not.toHaveClass('btn-quiet');
  });

  it("puts a stage's own door between the two, as the same button", async () => {
    const between = vi.fn();
    render(
      <PageTurn
        back={{ label: 'Back: Heritage', onClick: vi.fn() }}
        between={{ label: 'Restart: Clear All Choices', onClick: between }}
        next={{ label: 'Next: Path', onClick: vi.fn() }}
      />
    );
    const doors = screen.getAllByRole('button');
    expect(doors.map((door) => door.textContent)).toEqual([
      'Back: Heritage',
      'Restart: Clear All Choices',
      'Next: Path',
    ]);
    expect(new Set(doors.map((door) => door.className))).toEqual(new Set(['btn']));
    await userEvent.click(doors[1]);
    expect(between).toHaveBeenCalledTimes(1);
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
    expect(screen.getByRole('heading', { name: 'CG selections' })).toBeInTheDocument();
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

  it('a read-only row has no steppers but keeps the grid cell they occupy (#4457)', () => {
    const { container } = render(
      <StatRow id="lbl-occult" name="Occult" value={20} step={10} readOnly />
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    const row = container.querySelector('.stat-row');
    expect(row?.children).toHaveLength(3);
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
