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

A second, independent "what counts as prose" list is ``PROSE_KEYS`` in
``tools/lint_identifier_dashes.py`` - that one is a fast substring check guarding
the em-dash-in-identifiers linter, this one is exhaustive per content model field
and drives the credit backlog report. They already disagree in one spot
(``narration_snippet`` here vs ``narrative_snippet`` there); do not assume they
agree, and do not merge them - they serve different callers.

``prose_fields_for`` (below) is the one function in this module that touches
Django, and it defers the import inside the function body so the module as a
whole stays importable without a configured Django: the lore repo's write
editor imports this module directly, outside the Django project, and only
needs the two frozensets above.
"""

from __future__ import annotations

#: Authored text a player, or a GM at the table, actually reads.
PROSE_FIELD_NAMES = frozenset(
    {
        "announce_template",
        "arrival_verb",
        "authored_ic_framing",
        "custom_description",
        "default_description_template",
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
        "capture_cell_description",
        "capture_clue_description",
        "instance_description",
        "legend_description_template",
        "lore_content",
        "mechanical_description",
        "mechanics_content",
        "narration_snippet",
        "hit_narration",
        "miss_narration",
        "narrative_prose",
        "observer_description",
        "outcome_text",
        "player_description",
        "position_description",
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
#: ``notes``/``help_text`` are staff scratch space, not player-facing writing
#: (``CGExplanation.help_text``'s own field ``help_text=`` kwarg calls it a
#: "Reminder of which CG stage uses this key"); ``title``, ``label`` and
#: ``display_name`` are display identifiers, not prose.
NON_PROSE_TEXT_FIELDS = frozenset(
    {
        "action_key",
        "admin_notes",
        "base_action_key",
        "capture_cell_name",
        "capture_clue_name",
        "cloudinary_public_id",
        "cloudinary_url",
        "color_hex",
        "crest_asset",
        "display_name",
        "draft_validator_path",
        "fatigue_category",
        "gm_notes",
        "help_text",
        "icon",
        "icon_name",
        "icon_url",
        "instance_name",
        "key",
        "label",
        "latin_name",
        "name",
        "name_override",
        "notes",
        "position_name",
        "position_name_b",
        "ref",
        "reward_value",
        "service_function_path",
        "slug",
        "target_object_name",
        "title",
        "variable_name",
        "variant_name",
    }
)


def prose_fields_for(model) -> list[str]:
    """Names of *model*'s prose fields, in field-declaration order.

    The classification the coverage tests enforce: a CharField/TextField
    without choices whose name is in PROSE_FIELD_NAMES. Promoted from
    test_prose_credits._text_fields so production code (the authoring
    workbench, #3019) and the guard tests share one definition.
    """
    from django.db import models as dj_models  # noqa: PLC0415

    out: list[str] = []
    for field in model._meta.get_fields():  # noqa: SLF001
        if not isinstance(field, (dj_models.CharField, dj_models.TextField)):
            continue
        if field.choices:
            continue
        if field.name in PROSE_FIELD_NAMES:
            out.append(field.name)
    return out
