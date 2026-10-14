/**
 * How the composer reads the start of a line (#4346, ruled 2026-10-13).
 *
 * MU* players mark a command with `/`, `@` or `+`. `@` also addresses people
 * (`@Nyx,@Bob waves`), so a person present always wins; an `@` word that names
 * nobody here and no command the character has is held in the composer, never
 * posted and never eaten. First match wins:
 *
 * | Line starts with                    | Reading                               |
 * |-------------------------------------|---------------------------------------|
 * | `//`                                | prose with one literal `/`            |
 * | `/`                                 | the command after the slash           |
 * | `@@` or `++`                        | prose with one literal `@` or `+`     |
 * | `+` and a digit                     | prose (`+1`)                          |
 * | `+` and anything else               | a command, sent as typed              |
 * | `@` and the name of someone here    | prose addressed to them               |
 * | `@` and a command the character has | a command, sent as typed              |
 * | `@` and anything else               | held                                  |
 *
 * In a target list (`@Nyx,@Bob waves`) every name has to be someone here.
 */

/** A name character, as Python's Unicode `\w` plus the hyphen the server's token allows. */
const NAME_CHARS = '[\\p{L}\\p{N}_-]+';
/**
 * Mirrors the server's `_TARGET_PREFIX_RE` (`src/commands/parsing.py`): a
 * comma-separated `@name` list, whitespace, then the rest of the line.
 */
const TARGET_LIST = new RegExp(
  `^(@${NAME_CHARS}(?:\\s*,\\s*@${NAME_CHARS})*)\\s+([\\s\\S]+)$`,
  'u'
);
/** A leading `@word` with no list after it (`@who`, `@desc/edit here`, `@Nyx`). */
const LEADING_AT_WORD = new RegExp(`^@(${NAME_CHARS})`, 'u');
const NAME_WORD = new RegExp(NAME_CHARS, 'gu');
const DRAFT_KEPT = 'Your draft is kept.';

export interface ComposerLineContext {
  /** The people here, by the names the room list shows (worn faces, never keys). */
  people: readonly string[];
  /** Every name this character can type a command by (`Session.commandNames`). */
  commandNames: readonly string[];
}

export type ComposerLine =
  /** Sent over the socket exactly as `line`. */
  | { kind: 'command'; line: string }
  | {
      kind: 'prose';
      /**
       * What follows the mode's verb on the socket (`pose <socketText>`). A `@@`
       * stays doubled: the server's target parser reads it as the escape.
       */
      socketText: string;
      /** What the room reads: every escape removed. For the paths that parse nothing. */
      spoken: string;
      /** The leading `@` names, when the line opens with a target list. */
      targets: string[];
      /** `spoken` without that list, for the pose endpoint's `target_names` form. */
      body: string;
    }
  | {
      kind: 'held';
      reason: string;
      hint: string;
      /**
       * Whether more follows the `@` word. A lone `@wor` at the end of the line may
       * still be mid-word, so the note waits for a send attempt there.
       */
      settled: boolean;
    };

function prose(socketText: string, spoken = socketText): ComposerLine {
  return { kind: 'prose', socketText, spoken, targets: [], body: spoken };
}

/** Every way the room list lets a player write a person: each word, or the whole name hyphenated. */
function personWords(people: readonly string[]): Set<string> {
  const words = new Set<string>();
  for (const person of people) {
    const name = person.trim().toLowerCase();
    if (!name) continue;
    words.add(name.replace(/\s+/g, '-'));
    for (const word of name.match(NAME_WORD) ?? []) words.add(word);
  }
  return words;
}

function joinWithOr(names: string[]): string {
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(', ')} or ${names[names.length - 1]}`;
}

function heldForWord(word: string, settled: boolean): ComposerLine {
  return {
    kind: 'held',
    reason: `Nobody called ${word} is here, and you have no ${word} command.`,
    hint: DRAFT_KEPT,
    settled,
  };
}

function readAtLine(trimmed: string, context: ComposerLineContext): ComposerLine {
  const people = personWords(context.people);
  const commands = new Set(context.commandNames);
  const isPerson = (name: string) => people.has(name.toLowerCase());
  const isCommand = (name: string) => commands.has(name.toLowerCase());

  const list = TARGET_LIST.exec(trimmed);
  if (list) {
    const names = list[1].split(',').map((name) => name.trim().slice(1));
    const body = list[2];
    if (names.length === 1 && !isPerson(names[0])) {
      return isCommand(names[0]) ? { kind: 'command', line: trimmed } : heldForWord(names[0], true);
    }
    const missing = names.filter((name) => !isPerson(name));
    if (missing.length > 0) {
      return {
        kind: 'held',
        reason: `Nobody called ${joinWithOr(missing)} is here.`,
        hint: DRAFT_KEPT,
        settled: true,
      };
    }
    return { kind: 'prose', socketText: trimmed, spoken: trimmed, targets: names, body };
  }

  const word = LEADING_AT_WORD.exec(trimmed)?.[1];
  if (!word) return prose(trimmed);
  if (isPerson(word)) return prose(trimmed);
  if (isCommand(word)) return { kind: 'command', line: trimmed };
  return heldForWord(word, trimmed.length > word.length + 1);
}

/** Reads a trimmed composer line. Commands mode (staff) sends as typed and never comes here. */
export function readComposerLine(trimmed: string, context: ComposerLineContext): ComposerLine {
  if (trimmed.startsWith('//')) return prose(trimmed.slice(1));
  if (trimmed.startsWith('/')) return { kind: 'command', line: trimmed.slice(1).trim() };
  if (trimmed.startsWith('@@')) return prose(trimmed, trimmed.slice(1));
  if (trimmed.startsWith('++')) return prose(trimmed.slice(1));
  if (trimmed.startsWith('+')) {
    const next = trimmed.charAt(1);
    if (next === '' || /\s|\d/u.test(next)) return prose(trimmed);
    return { kind: 'command', line: trimmed };
  }
  if (trimmed.startsWith('@')) return readAtLine(trimmed, context);
  return prose(trimmed);
}
