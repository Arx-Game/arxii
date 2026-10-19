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
 * | `+` and a letter                    | a command, sent as typed              |
 * | `+` and anything else (`+1`, `+_+`) | prose                                 |
 * | `@` and the name of someone here    | prose addressed to them               |
 * | `@` and a command the character has | a command, sent as typed              |
 * | `@` and anything else               | held                                  |
 *
 * In a target list (`@Nyx,@Bob waves`) every name has to be someone here.
 * Nothing is held where `@` addresses nobody (a page, a whisper, a structured
 * say) or while the room is not known yet: there the line is prose, unless its
 * `@` word is a command.
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
const PLUS_COMMAND = /^\+\p{L}/u;
const DRAFT_KEPT = 'Your draft is kept.';

export interface ComposerLineContext {
  /**
   * The people here, by the names the room list shows (worn faces, never keys),
   * or `null` while the room is not known: then nobody can be called absent.
   */
  people: readonly string[] | null;
  /** Every name this character can type a command by (`Session.commandNames`). */
  commandNames: readonly string[];
  /** Whether `@` addresses people in this mode (pose, emit), so an unknown name is held. */
  addressing: boolean;
}

export type ComposerLine =
  /** Sent over the socket exactly as `line`. */
  | { kind: 'command'; line: string }
  | {
      kind: 'prose';
      /**
       * What follows a parsing verb on the socket (`pose <socketText>`). A `@@`
       * stays doubled: the server's target parser reads it as the escape.
       */
      socketText: string;
      /** What the room reads: every escape removed. For the paths that parse nothing. */
      spoken: string;
      /**
       * The leading `@` names when the line opens with a list of people here,
       * once each. The text keeps them: the server resolves names by key, which
       * the room list does not show, so taking one out could lose it.
       */
      targets: string[];
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

function prose(socketText: string, spoken = socketText, targets: string[] = []): ComposerLine {
  return { kind: 'prose', socketText, spoken, targets };
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

/** Each name once, compared without case, keeping the first spelling. */
export function uniqueNames(names: readonly string[]): string[] {
  const seen = new Set<string>();
  return names.filter((name) => {
    const key = name.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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

/** A list addresses people only: every name must be present. */
function readTargetList(trimmed: string, names: string[], people: Set<string>): ComposerLine {
  const missing = names.filter((name) => !people.has(name.toLowerCase()));
  if (missing.length === 0) return prose(trimmed, trimmed, uniqueNames(names));
  return {
    kind: 'held',
    reason: `Nobody called ${joinWithOr(missing)} is here.`,
    hint: DRAFT_KEPT,
    settled: true,
  };
}

/** With no known audience, @ can select a command but cannot name someone absent. */
function readUnscopedAtLine(
  trimmed: string,
  word: string,
  names: string[] | null,
  context: ComposerLineContext
): ComposerLine {
  if (context.commandNames.includes(word.toLowerCase()) && (names?.length ?? 1) === 1)
    return { kind: 'command', line: trimmed };
  return prose(trimmed, trimmed, context.addressing && names ? uniqueNames(names) : []);
}

function readAtLine(trimmed: string, context: ComposerLineContext): ComposerLine {
  const commands = new Set(context.commandNames);
  const isCommand = (name: string) => commands.has(name.toLowerCase());
  // Where `@` addresses nobody, or the room is not known, nobody can be absent.
  const people = context.addressing && context.people ? personWords(context.people) : null;
  const isPerson = (name: string) => people?.has(name.toLowerCase()) ?? false;

  const list = TARGET_LIST.exec(trimmed);
  const names = list ? list[1].split(',').map((name) => name.trim().slice(1)) : null;
  const word = names?.[0] ?? LEADING_AT_WORD.exec(trimmed)?.[1];
  if (!word) return prose(trimmed);

  if (!people) {
    return readUnscopedAtLine(trimmed, word, names, context);
  }

  if (names && names.length > 1) {
    return readTargetList(trimmed, names, people);
  }
  if (isPerson(word)) return prose(trimmed, trimmed, names ? [word] : []);
  if (isCommand(word)) return { kind: 'command', line: trimmed };
  return heldForWord(word, names !== null || trimmed.length > word.length + 1);
}

/** Reads a trimmed composer line. Commands mode (staff) sends as typed and never comes here. */
export function readComposerLine(trimmed: string, context: ComposerLineContext): ComposerLine {
  if (trimmed.startsWith('//')) return prose(trimmed.slice(1));
  if (trimmed.startsWith('/')) return { kind: 'command', line: trimmed.slice(1).trim() };
  if (trimmed.startsWith('@@')) return prose(trimmed, trimmed.slice(1));
  if (trimmed.startsWith('++')) return prose(trimmed.slice(1));
  if (trimmed.startsWith('+')) {
    return PLUS_COMMAND.test(trimmed) ? { kind: 'command', line: trimmed } : prose(trimmed);
  }
  if (trimmed.startsWith('@')) return readAtLine(trimmed, context);
  return prose(trimmed);
}
