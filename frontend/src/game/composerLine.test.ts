import { describe, expect, it } from 'vitest';

import { readComposerLine, uniqueNames } from './composerLine';
import type { ComposerLineContext } from './composerLine';

// Room-list names in the shapes `get_display_name(looker)` really produces:
// a plain name, a multi-word key, a trainer NPC, an anonymous sdesc.
const here: ComposerLineContext = {
  people: ['Nyx', 'Bob', 'Crucible Mundi', 'Éowyn', 'Path of the Voice Trainer', 'a man in a mask'],
  commandNames: ['look', 'who', 'sheet', 'friend', 'desc', 'set', 'name', 'gm'],
  addressing: true,
};
const player: ComposerLineContext = { ...here, commandNames: ['look', 'who', 'sheet', 'friend'] };
const page: ComposerLineContext = { ...player, addressing: false };
const roomUnknown: ComposerLineContext = { ...player, people: null };

describe('readComposerLine (#4346)', () => {
  describe('the slash', () => {
    it('reads / as the command after it', () => {
      expect(readComposerLine('/look', here)).toEqual({ kind: 'command', line: 'look' });
    });

    it('reads // as prose with one literal slash', () => {
      expect(readComposerLine('//shrugs', here)).toMatchObject({
        kind: 'prose',
        socketText: '/shrugs',
        spoken: '/shrugs',
      });
    });
  });

  describe('the plus', () => {
    it('reads + and a word as a command, sent as typed', () => {
      expect(readComposerLine('+friend Nyx', here)).toEqual({
        kind: 'command',
        line: '+friend Nyx',
      });
    });

    it('reads +word as a command even when the character lacks it, since + never addresses anyone', () => {
      expect(readComposerLine('+grievance', player)).toEqual({
        kind: 'command',
        line: '+grievance',
      });
    });

    it('reads + and a digit, punctuation or a space as prose', () => {
      for (const line of ['+1 to that', '+_+ wow', '+. agreed', '+ also this']) {
        expect(readComposerLine(line, here)).toMatchObject({ kind: 'prose', spoken: line });
      }
    });

    it('reads ++ as prose with one literal plus', () => {
      expect(readComposerLine('++friend is a word', here)).toMatchObject({
        kind: 'prose',
        socketText: '+friend is a word',
        spoken: '+friend is a word',
      });
    });
  });

  describe('the at sign, where it addresses people', () => {
    it('addresses someone here, keeping the name in the text', () => {
      expect(readComposerLine('@Nyx waves', here)).toEqual({
        kind: 'prose',
        socketText: '@Nyx waves',
        spoken: '@Nyx waves',
        targets: ['Nyx'],
      });
    });

    it('addresses several people here, each once', () => {
      expect(readComposerLine('@Nyx, @bob,@nyx waves', here)).toMatchObject({
        kind: 'prose',
        targets: ['Nyx', 'bob'],
      });
    });

    it('lets a person win over a command of the same name', () => {
      const lookAlike: ComposerLineContext = { ...here, people: ['Look'] };
      expect(readComposerLine('@Look over here', lookAlike)).toMatchObject({
        kind: 'prose',
        targets: ['Look'],
      });
    });

    it('matches any word of a name the room list shows, and Unicode names', () => {
      expect(readComposerLine('@Crucible nods', here)).toMatchObject({ targets: ['Crucible'] });
      expect(readComposerLine('@Crucible-Mundi nods', here)).toMatchObject({
        targets: ['Crucible-Mundi'],
      });
      expect(readComposerLine('@éowyn smiles', here)).toMatchObject({ targets: ['éowyn'] });
    });

    it('never holds what the @ autocomplete inserts for a multi-word name', () => {
      expect(readComposerLine('@Path of the Voice Trainer hello', here)).toMatchObject({
        kind: 'prose',
        spoken: '@Path of the Voice Trainer hello',
      });
      expect(readComposerLine('@a man in a mask, a word', here)).toMatchObject({ kind: 'prose' });
    });

    it('reads @command as the command, sent as typed', () => {
      expect(readComposerLine('@desc here = A cold room', here)).toEqual({
        kind: 'command',
        line: '@desc here = A cold room',
      });
      expect(readComposerLine('@sheet', here)).toEqual({ kind: 'command', line: '@sheet' });
      expect(readComposerLine('@desc/edit here', here)).toEqual({
        kind: 'command',
        line: '@desc/edit here',
      });
    });

    it('holds an @ word that is neither someone here nor a command the character has', () => {
      expect(readComposerLine('@desc here = A cold room', player)).toEqual({
        kind: 'held',
        reason: 'Nobody called desc is here, and you have no desc command.',
        hint: 'Your draft is kept.',
        settled: true,
      });
    });

    it('holds a target list naming anyone who is not here', () => {
      expect(readComposerLine('@Nyx,@Gone,@Lost waves', here)).toEqual({
        kind: 'held',
        reason: 'Nobody called Gone or Lost is here.',
        hint: 'Your draft is kept.',
        settled: true,
      });
    });

    it('holds a list even when one of its names is a command', () => {
      expect(readComposerLine('@desc,@Nyx hi', here)).toMatchObject({
        kind: 'held',
        reason: 'Nobody called desc is here.',
      });
    });

    it('waits for a send before calling a lone unknown word at the end of the line settled', () => {
      expect(readComposerLine('@Ny', player)).toMatchObject({ kind: 'held', settled: false });
      expect(readComposerLine('@xyz/edit', player)).toMatchObject({ kind: 'held', settled: true });
    });

    it('reads a lone @person as prose with nobody addressed, as the server does', () => {
      expect(readComposerLine('@Nyx', here)).toMatchObject({ kind: 'prose', targets: [] });
    });

    it('reads @@ as prose with one literal at sign, kept doubled for the server parser', () => {
      expect(readComposerLine('@@everyone gets a drink', here)).toEqual({
        kind: 'prose',
        socketText: '@@everyone gets a drink',
        spoken: '@everyone gets a drink',
        targets: [],
      });
    });

    it('reads an @ followed by a space as prose', () => {
      expect(readComposerLine('@ the docks', here)).toMatchObject({ kind: 'prose' });
    });
  });

  describe('the at sign, where it addresses nobody', () => {
    it('never holds a page or whisper line for naming someone elsewhere', () => {
      expect(readComposerLine('@Alice said you were late', page)).toEqual({
        kind: 'prose',
        socketText: '@Alice said you were late',
        spoken: '@Alice said you were late',
        targets: [],
      });
    });

    it('still reads @command as the command there', () => {
      expect(readComposerLine('@sheet', page)).toEqual({ kind: 'command', line: '@sheet' });
    });
  });

  describe('before the room is known', () => {
    it('calls nobody absent: the line is prose, its names still addressed', () => {
      expect(readComposerLine('@Nyx waves', roomUnknown)).toEqual({
        kind: 'prose',
        socketText: '@Nyx waves',
        spoken: '@Nyx waves',
        targets: ['Nyx'],
      });
    });

    it('keeps a multi-name list as prose even when its first name is a command', () => {
      const line = '@who,@Nyx,@nyx waves';
      expect(readComposerLine(line, roomUnknown)).toEqual({
        kind: 'prose',
        socketText: line,
        spoken: line,
        targets: ['who', 'Nyx'],
      });
      expect(readComposerLine(line, page)).toMatchObject({ kind: 'prose', targets: [] });
    });

    it('still reads @command as the command', () => {
      expect(readComposerLine('@who', roomUnknown)).toEqual({ kind: 'command', line: '@who' });
    });
  });

  it('reads any other line as prose', () => {
    expect(readComposerLine('look', here)).toEqual({
      kind: 'prose',
      socketText: 'look',
      spoken: 'look',
      targets: [],
    });
  });
});

describe('uniqueNames', () => {
  it('keeps the first spelling of each name, compared without case', () => {
    expect(uniqueNames(['Nyx', 'Bob', 'nyx', 'NYX', 'bob', 'Ana'])).toEqual(['Nyx', 'Bob', 'Ana']);
  });
});
