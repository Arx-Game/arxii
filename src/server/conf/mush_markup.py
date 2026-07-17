"""MUSH-style ``%r``/``%t`` markup conversion for telnet input.

Telnet is line-oriented: each line the client sends is a separate input, so
``%r`` is how MU* players embed a newline into a single line of input (the
near-universal MUSH/MUX convention). This module converts that markup to real
newlines/tabs at the telnet input boundary; see ``server.conf.inputfuncs.text``.

Modern Evennia does not parse ``%r``/``%t`` (its ANSI map only has ``|/`` and
``|-``), and we deliberately convert at *input* rather than aliasing at output,
so stored text carries real ``\\n``/``\\t`` and renders on every surface (telnet,
live web messages, and REST-read fields).
"""

_NEWLINE = ("r", "R")
_TAB = ("t", "T")


def normalize_mush_markup(text: str) -> str:
    """Convert MUSH ``%r``/``%t`` markup to real newlines/tabs.

    Single left-to-right pass so escapes are unambiguous:

    - ``%r`` / ``%R`` -> newline
    - ``%t`` / ``%T`` -> tab
    - ``%%``          -> a literal ``%`` (lets a user type a real ``%r`` as ``%%r``)
    - ``%`` followed by anything else, or a trailing lone ``%`` -> left unchanged
    """
    if "%" not in text:
        return text
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "%" and i + 1 < length:
            nxt = text[i + 1]
            if nxt in _NEWLINE:
                out.append("\n")
            elif nxt in _TAB:
                out.append("\t")
            elif nxt == "%":
                out.append("%")
            else:
                out.append(char)
                out.append(nxt)
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)
