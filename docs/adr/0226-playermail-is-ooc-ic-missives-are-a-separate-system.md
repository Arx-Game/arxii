# PlayerMail is OOC between players; IC missives are a separate system

Per the #3303 ruling, `world.roster.PlayerMail` reverts to its original identity: the
out-of-character, player-to-player message surface, tenure-routed so the recipient is
addressed and displayed as "the current player of Character X" rather than by account
(unchanged since #124/#146, before the roster restructure). In-character correspondence
(#3289) is a distinct, not-yet-built system with its own storage - a sent missive is
authored by a persona, not a tenure; carries an in-fiction transmission mechanism
(courier, sending spell, ...) and in-character game time, not real-world `sent_date`;
and models deliveries as a separate concept from read state. We rejected renaming or
otherwise hammering `PlayerMail` into that shape (adding a persona/transmission/IC-time
layer onto the existing model, or renaming it to `Letter`) - PlayerMail's anonymity
mechanism (tenure routing) and IC missives' authorship mechanism (persona identity) are
opposite design goals, and conflating them would either break player anonymity on mail
or force IC missives through an anonymity layer that makes no sense for in-fiction mail.

> Status: accepted · Source: #3303 (supersedes ADR-0116; see #3289 for the IC system)
