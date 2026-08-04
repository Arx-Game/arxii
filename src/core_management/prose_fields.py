"""Which text fields on content models hold prose, and which do not (#2980).

Every ``CharField``/``TextField`` on a model in ``CONTENT_MODELS`` is named in
exactly one of the two sets below. A field in neither fails
``test_prose_credits.ProseFieldClassificationTests``, so adding a text field to a
content model forces a decision: is this something a person writes for players to
read, or is it an identifier, a label, or a technical path?

That decision drives two things: whether the model inherits ``CreditedContent``
(so someone can be credited for it), and whether the backlog report counts it.

A name heuristic was tried first and silently missed nine models carrying real
player-facing prose, which is why this is an exhaustive list rather than a
pattern. Django-free on purpose: ``prose_report`` imports it and must run without
a configured Django.
"""

from __future__ import annotations

#: Authored text a player, or a GM at the table, actually reads.
PROSE_FIELD_NAMES = frozenset(
    {
        "announce_template",
        "arrival_verb",
        "authored_ic_framing",
        "custom_description",
        "departure_verb",
        "description",
        "description_reversed",
        "description_template",
        "epilogue",
        "example",
        "fit_notes",
        "flavor_text",
        "followon_message",
        "frame_narrative",
        "goal",
        "guidance_text",
        "help_text",
        "instance_description",
        "lore_content",
        "mechanics_content",
        "narration_snippet",
        "narrative_prose",
        "observer_description",
        "outcome_text",
        "player_description",
        "prompt",
        "prose",
        "selection_criteria",
        "styleable_adjective",
        "summary",
        "text",
        "tooltip",
        "windup_telegraph",
    }
)

#: Identifiers, labels, staff notes and technical paths. Nobody is credited for
#: these and the backlog report never counts them. ``gm_notes``/``admin_notes``/
#: ``notes`` are staff scratch space, not player-facing writing; ``title``,
#: ``label`` and ``display_name`` are display identifiers, not prose.
NON_PROSE_TEXT_FIELDS = frozenset(
    {
        "action_key",
        "admin_notes",
        "cloudinary_public_id",
        "cloudinary_url",
        "color_hex",
        "crest_asset",
        "display_name",
        "draft_validator_path",
        "gm_notes",
        "icon",
        "icon_name",
        "icon_url",
        "instance_name",
        "key",
        "label",
        "latin_name",
        "name",
        "notes",
        "ref",
        "reward_value",
        "service_function_path",
        "slug",
        "target_object_name",
        "title",
        "variable_name",
    }
)
