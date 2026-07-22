"""
Command sets

All commands in the game must be grouped in a cmdset.  A given command
can be part of any number of cmdsets and cmdsets can be added/removed
and merged onto entities at runtime.

To create new commands to populate the cmdset, see
`commands/command.py`.

This module wraps the default command sets of Evennia; overloads them
to add/remove commands from the default lineup. You can create your
own cmdsets by inheriting from them or directly from `evennia.CmdSet`.

"""

from evennia import default_cmds

from commands.account.account_info import CmdAccount, CmdRoster
from commands.account.character_switching import CmdCharacters, CmdIC
from commands.account.prompt_reply import CmdPromptReply
from commands.account.sheet import CmdSheet
from commands.account.staff_contact import CmdPetition
from commands.agriculture import CmdHarvest
from commands.alterations import CmdMageScar
from commands.assets import CmdIntroduce
from commands.battle import CmdBattle
from commands.canon_review import CmdCanonReview
from commands.captivity import CmdDemandRansom
from commands.ceremonies import CmdCeremony
from commands.combat import CmdClashCommit, CmdDeclareTechnique
from commands.combat_maneuvers import CmdCombat
from commands.comfort import CmdComfort
from commands.companion import CmdCompanion
from commands.conditions import CmdTreatCondition
from commands.consent import (
    CmdAccept,
    CmdDeceive,
    CmdDeny,
    CmdEntrance,
    CmdFlirt,
    CmdIntimidate,
    CmdPerform,
    CmdPersuade,
    CmdRestoreSense,
    CmdSeduce,
)
from commands.consent_preferences import CmdConsent
from commands.covenant import CmdCovenant
from commands.crafting import CmdCraft
from commands.crafting_station import CmdLabStation
from commands.currency import CmdDeposit, CmdSecure, CmdSteal
from commands.deeds import CmdDeed
from commands.defenses import CmdDefense
from commands.domains import CmdDomain
from commands.door import CmdBreak, CmdLock, CmdPick, CmdUnlock
from commands.dramatic_moments import CmdMoment
from commands.dreams import CmdSleep  # #2290
from commands.duels import CmdDuel
from commands.durance import CmdDurance
from commands.encounter import CmdEncounter
from commands.endorse import CmdEndorse, CmdPoses
from commands.evennia_overrides.builder import CmdDig, CmdLink, CmdOpen, CmdUnlink
from commands.evennia_overrides.communication import (
    CmdEmit,
    CmdMutter,
    CmdPage,
    CmdPemit,
    CmdPose,
    CmdSay,
    CmdTabletalk,
    CmdWhisper,
)
from commands.evennia_overrides.items import (
    CmdPut,
    CmdRemove,
    CmdUndress,
    CmdUse,
    CmdWear,
    CmdWithdraw,
)
from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive, CmdHome
from commands.evennia_overrides.perception import CmdInventory, CmdLook
from commands.events import CmdEvent
from commands.fashion import CmdJudgePresentation
from commands.fatigue import CmdRest
from commands.form import CmdForm
from commands.functionary import CmdFunctionary
from commands.gemit import CmdGemit
from commands.gift_learning import CmdLearn
from commands.gm_ops import CmdGMDashboard, CmdGMIdle
from commands.gm_props import CmdStage
from commands.gm_tables import CmdGMTable
from commands.gmtrust import CmdGMTrust
from commands.goals import CmdGoal  # #1350 — goal authoring namespace.
from commands.grant_distinction import CmdGrantDistinction
from commands.grant_item import CmdGrantItem
from commands.guard import CmdGuard  # #2178
from commands.hire import CmdHire
from commands.identification import CmdIdentify  # #1107
from commands.imbue import CmdImbue
from commands.investigation import CmdSearch  # #1866
from commands.journals import CmdJournal
from commands.locations import CmdRoom
from commands.market import CmdMarket
from commands.missions import CmdMission
from commands.motif import CmdMotif
from commands.offer_response import CmdDecline
from commands.organizations import CmdOrg
from commands.outfit import CmdOutfit  # #1866
from commands.persona import CmdPersona
from commands.places import CmdPlaces  # #1866
from commands.portals import CmdPortalAnchor  # #2222
from commands.positions import CmdPosition  # #2005
from commands.presence import CmdAfk, CmdHide
from commands.progression import CmdProgressionUnlock, CmdTraining
from commands.progression_rewards import CmdKudos, CmdPathIntent, CmdRandomScene, CmdVote
from commands.projects import CmdProject
from commands.react import CmdReact
from commands.relationships import CmdRelationship
from commands.resonance import CmdResonance
from commands.retire import CmdRetire  # #2287
from commands.ritual import CmdRitual
from commands.sanctum import CmdSanctum
from commands.scene import CmdScene
from commands.seance import CmdSeance
from commands.setsituation import CmdSetSituation
from commands.setstage import CmdSetStage
from commands.sheet_request import CmdSheetRequest  # #2628 — sheet-update requests.
from commands.ships import CmdShip
from commands.signature import CmdSignature
from commands.social.accusations import CmdAccuse, CmdFrame
from commands.social.blocking import (
    CmdBlock,
    CmdBlockList,
    CmdMute,
    CmdShareBlock,
    CmdUnblock,
    CmdUnmute,
)
from commands.social.entrance_flourish import CmdEnter, CmdFlourish
from commands.social.evidence import CmdEvidence
from commands.social.friends import CmdFriend, CmdFriends, CmdUnfriend
from commands.social.gossip import CmdGossip
from commands.social.grievance import CmdGrievance
from commands.social.rivals import CmdRival, CmdRivals, CmdUnrival
from commands.social.soul_tether import CmdSineater, CmdTether
from commands.social.tidings import CmdTidings
from commands.speaker_queue import CmdLine  # #2356
from commands.sphinx import CmdSphinx  # #2640
from commands.story import CmdStory
from commands.story_rooms import CmdJoinRoom, CmdLeaveRoom, CmdSceneRoom  # #2450
from commands.technique import CmdTechnique
from commands.threads import CmdThreads
from commands.travel import CmdTravel  # #2163
from commands.vault import CmdVault
from commands.voyages import CmdVoyage  # #1855
from commands.wake import CmdWake  # #2287
from commands.weather import CmdTime
from commands.weave import CmdWeaveThread
from commands.where import CmdWhere
from commands.who import CmdWho
from commands.windows import CmdCloseWindow, CmdOpenWindow


class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """
    The `CharacterCmdSet` contains general in-game commands like `look`,
    `get`, etc available on in-game Character objects. It is merged with
    the `AccountCmdSet` when an Account puppets a Character.
    """

    key = "DefaultCharacter"

    def at_cmdset_creation(self) -> None:
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        # Replace Evennia's basic interaction commands with flow-based versions.
        for cmdname in (
            "look",
            "get",
            "drop",
            "give",
            "home",
            "inventory",
            "say",
            "whisper",
            "pose",
            "emote",
            "dig",
            "open",
            "link",
            "unlink",
        ):
            self.remove(cmdname)

        # Each command is a thin telnet shell; register them by iterating a
        # tuple so this method stays well under ruff's statement ceiling
        # (PLR0915) as the command roster grows.
        command_classes = (
            CmdLook,
            CmdGet,
            CmdDrop,
            CmdGive,
            CmdWear,
            CmdRemove,
            CmdUndress,
            CmdPut,
            CmdWithdraw,
            CmdUse,
            # #1909 — physical-currency interplay: deposit/steal/secure containers.
            CmdDeposit,
            CmdSteal,
            CmdSecure,
            CmdHome,
            CmdInventory,
            CmdSay,
            CmdWhisper,
            CmdPose,
            CmdEmit,
            CmdPemit,
            CmdMutter,
            CmdTabletalk,
            CmdLock,
            CmdUnlock,
            CmdPick,
            CmdBreak,
            CmdOpenWindow,
            CmdCloseWindow,
            CmdRitual,
            # #1700 — Durance status/intent/convene telnet namespace.
            CmdDurance,
            # #1349 — telnet face of the mission play services (resolve/abandon/group pick+vote).
            CmdMission,
            # #1497 — sanctum lifecycle telnet namespace (install/homecoming/purging/
            # weave/dissolve/absorb/sever).
            CmdSanctum,
            # #1918 — companion lifecycle telnet namespace (bind/fight/deploy/release).
            CmdCompanion,
            # #1582 — signature-bonus selection namespace (set/clear/list).
            CmdSignature,
            # #2030 — motif style-binding namespace (bindstyle/unbindstyle/list).
            CmdMotif,
            # #2183 — dramatic-moment suggestion inbox (suggestions/confirm/dismiss).
            CmdMoment,
            CmdWeaveThread,
            CmdImbue,
            # #1490 — telnet face of ResolveAlterationAction; list/resolve Mage Scars.
            CmdMageScar,
            CmdEnter,
            CmdFlourish,
            CmdThreads,
            CmdEndorse,
            CmdPoses,
            CmdReact,
            CmdJudgePresentation,
            CmdIntimidate,
            CmdAccept,
            CmdDecline,
            CmdDeny,
            CmdPersuade,
            CmdDeceive,
            CmdFlirt,
            CmdSeduce,
            CmdPerform,
            CmdEntrance,
            CmdRestoreSense,
            CmdTreatCondition,
            # #1487 - telnet consent preference management namespace.
            CmdConsent,
            CmdDig,
            CmdOpen,
            CmdLink,
            CmdUnlink,
            # #1278 — block/mute social controls (the telnet face of the persona menu).
            CmdBlock,
            CmdUnblock,
            CmdShareBlock,
            CmdMute,
            CmdUnmute,
            CmdBlockList,
            # Soul Tether lifecycle commands (#1343)
            CmdTether,
            CmdSineater,
            # #1429 — the telnet face of the secret-victim grievance prompt.
            CmdGrievance,
            # #1825 — manufacture a false scandal against a consenting target,
            # or doctor real evidence into a frame job at a Workshop of Iniquity.
            CmdAccuse,
            CmdFrame,
            CmdEvidence,
            # #1450 — the pull/browse face of the public-reaction tidings feed.
            CmdTidings,
            # #1572 — work the rumor mill at a social hub (plant/seek/suppress gossip).
            CmdGossip,
            # #1727 — the OOC friends list (add/remove/list) + watch-list.
            CmdFriend,
            CmdUnfriend,
            CmdFriends,
            CmdRival,
            CmdUnrival,
            CmdRivals,
            # #1463 — public presence/navigation: who's about, in coloured area paths.
            CmdWhere,
            # #1463 — online roster: who's online, by active persona, coarse idle.
            CmdWho,
            # #1463 — self-presence toggles: transient away + persistent quiet/hidden mode.
            CmdAfk,
            CmdHide,
            # #1491 — telnet face of RestAction; spend AP to become Well-Rested.
            CmdRest,
            # #2287 — telnet face of WakeAction; attempt to wake from unconsciousness.
            CmdWake,
            # #2290 — telnet face of SleepAction; voluntarily sleep to enter the dream realm.
            CmdSleep,
            # #2287 — telnet face of RetireCharacterAction; lay a dead character to rest.
            CmdRetire,
            # #2237 — telnet face of CollectFoodAction; harvest a field's food.
            CmdHarvest,
            # #1866 — telnet face of SearchAction; search for clues in a room.
            CmdSearch,
            # #1107 slice 5 — telnet face of IdentifyAction; see through a mask/disguise.
            CmdIdentify,
            # #1450 — the staff push face: hand-authored gemits scoped by reach.
            CmdGemit,
            # #2003 — staff canon-review queue (perm(Admin)).
            CmdCanonReview,
            # #2004 — GM dashboard + idle-tables listing.
            CmdGMDashboard,
            CmdGMIdle,
            # #1505 — basic telnet parity for GM-table admin (web is the primary surface).
            CmdGMTable,
            # #1496 — staff/GM technique authoring workbench (perm(Builder)).
            CmdTechnique,
            # Unified scene-adaptive cast (#1351)
            CmdDeclareTechnique,
            # Clash contribution (#1451)
            CmdClashCommit,
            # Shared combat verbs: combat <subverb> (#1453, #1452)
            CmdCombat,
            # PC-vs-PC duel lifecycle: duel <subverb> (#1492)
            CmdDuel,
            # Scene lifecycle telnet command (#1445)
            CmdScene,
            # Deed spread / deed story telnet namespace (#1503)
            CmdDeed,
            # #1493 — NPC-service hire/commission interaction loop.
            CmdHire,
            # #1766 — list/place/remove room Functionaries (place/remove staff-only).
            CmdFunctionary,
            # #1494/#1495 — GM encounter and story lifecycle telnet namespaces.
            CmdEncounter,
            CmdStory,
            # #2000 — GM trust-ladder: view/promote a GM's level (staff-gated).
            CmdGMTrust,
            # #1574 — project status + money donation (project/donate, +project).
            CmdProject,
            # #1500 — staff: demand a crowdfundable ransom for a held captive.
            CmdDemandRansom,
            # #707 — staff: ad-hoc narrative item grant (no shop/merchant system exists).
            CmdGrantItem,
            # #2037 — GM: award/rank-up a catalog Distinction (post-CG acquisition).
            CmdGrantDistinction,
            # #2628 — player/GM sheet-update request namespace.
            CmdSheetRequest,
            # #1470 — owner-gated room editor (name/description/public-private).
            CmdRoom,
            # #2178 — NPC guard assignment (assign/unassign/list).
            CmdGuard,
            # #1498 — staff set-the-stage: apply a position blueprint to the room.
            CmdSetStage,
            # #2450 — GM story rooms: spin up/close a temp scene room; join/leave a
            # granted story or scene room.
            CmdSceneRoom,
            CmdJoinRoom,
            CmdLeaveRoom,
            # #1895 — staff set-situation: instantiate a SituationTemplate into the room.
            CmdSetSituation,
            # #1514 — in-room comfort/weather readout (the mechanical surface).
            CmdComfort,
            # #1522 — IC time + local weather readout (`time`/`weather`).
            CmdTime,
            # #1111 — form shift/revert telnet namespace for alternate selves.
            CmdForm,
            # #1347 — list faces + wear-face active persona switch.
            CmdPersona,
            # #2295 — voluntary asset introduction (co-ownership).
            CmdIntroduce,
            # Training allocation and unlock purchase telnet surfaces.
            CmdTraining,
            CmdProgressionUnlock,
            # #2116 — gift/technique/thread-weaving acquisition namespace.
            CmdLearn,
            # #1350 — journal authoring namespace: write/respond/edit subverbs + list hub.
            CmdJournal,
            # #1350 — goal authoring namespace.
            CmdGoal,
            # #1485 — relationship-building namespace: impression/develop/capstone/
            # redistribute write verbs + list/show read surfaces.
            CmdRelationship,
            # #1499 — event lifecycle + invitee RSVP namespace: create/schedule/start/
            # complete/cancel/invite/rsvp verbs + list/show read surfaces.
            CmdEvent,
            # #2289 — ceremony rites: funeral/blessing/sermon open, offering,
            # speech, finish/abandon + the show read surface.
            CmdCeremony,
            # #1511 — organization membership lifecycle.
            CmdOrg,
            # #1348 — progression-reward telnet commands: kudos/vote/randomscene/pathintent.
            CmdKudos,
            CmdVote,
            CmdRandomScene,
            CmdPathIntent,
            # #1346 — covenant membership lifecycle telnet namespace.
            CmdCovenant,
            # #2239 — in-play domain management + office delegation.
            CmdDomain,
            # #1592 — battle system: GM lifecycle + player declare namespace.
            CmdBattle,
            # #1866 — facet/style attach/detach telnet namespace.
            CmdCraft,
            # #1866 — outfit CRUD + wear/undress/present telnet namespace.
            CmdOutfit,
            # #1866 — places join/leave telnet namespace.
            CmdPlaces,
            # #2356 — speaker queue (getinline) telnet namespace.
            CmdLine,
            # #2005 — tactical position graph: list/take/move telnet namespace.
            CmdPosition,
            # #2163 — "go there" travel: auto-walk to a character's location.
            CmdTravel,
            CmdVoyage,
            # #2222 — portal anchor install/dissolve namespace.
            CmdPortalAnchor,
            # #1234 — Lab crafting station install/upgrade/repair namespace.
            CmdLabStation,
            # #2177 — exit/room defense (bars/ward/alarm) install/upgrade/fund namespace.
            CmdDefense,
            # #2503 — GM improv stage-prop namespace (conjure a prop / tag a property).
            CmdStage,
            CmdMarket,
            # #1832 — ship commission/upgrade/repair/status namespace.
            CmdShip,
            # #2179 — vault access-list management namespace.
            CmdVault,
            # #2032 — spendable resonance balances + grant history (bare/history subverbs).
            CmdResonance,
            # #2640 — the Sphinx of Black Quartz's vow-suitability verdict.
            CmdSphinx,
        )
        for command_cls in command_classes:
            self.add(command_cls())


class AccountCmdSet(default_cmds.AccountCmdSet):
    """
    This is the cmdset available to the Account at all times. It is
    combined with the `CharacterCmdSet` when the Account puppets a
    Character. It holds game-account-specific commands, channel
    commands, etc.
    """

    key = "DefaultAccount"

    def at_cmdset_creation(self) -> None:
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        for cmdname in ("ic", "characters", "account", "page"):
            self.remove(cmdname)

        self.add(CmdIC())
        self.add(CmdCharacters())
        # #2393 — seance manifestation-offer inbox: offers/accept/decline,
        # account-scoped (reaches a retired honoree with no active puppet).
        self.add(CmdSeance())
        self.add(CmdAccount())
        self.add(CmdSheet())
        self.add(CmdPage())
        self.add(CmdPromptReply())
        # #2122 — own-status-only roster check (browsing stays web-first).
        self.add(CmdRoster())
        # #2288 — staff-contact pointer (filing stays web-first).
        self.add(CmdPetition())


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """
    Command set available to the Session before being logged in.  This
    holds commands like creating a new account, logging in, etc.
    """

    key = "DefaultUnloggedin"

    def at_cmdset_creation(self) -> None:
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #


class SessionCmdSet(default_cmds.SessionCmdSet):
    """
    This cmdset is made available on Session level once logged in. It
    is empty by default.
    """

    key = "DefaultSession"

    def at_cmdset_creation(self) -> None:
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        As and example we just add the empty base `Command` object.
        It prints some info.
        """
        super().at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
