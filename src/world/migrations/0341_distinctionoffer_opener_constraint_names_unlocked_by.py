# Hand-split from 0340 (#4846): the constraint step of expand/contract.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Re-add ``distinctionoffer_at_most_one_opener`` naming ``unlocked_by`` (#4846).

    Schema only, no backfill to run first: the pairs the constraint adds all read
    ``unlocked_by IS NULL OR <other opener> unset``, and 0340 left ``unlocked_by`` NULL
    on every existing row, so every row satisfies the new constraint as it stands.
    Separate from 0340 because a CHECK that pairs a column added nullable with an older
    column never shares a migration with that column (``0149``, 2026-09-24).
    """

    dependencies = [
        ("arxii", "0340_final_touches_chapter_and_crime_notes"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="distinctionoffer",
            name="distinctionoffer_at_most_one_opener",
        ),
        migrations.AddConstraint(
            model_name="distinctionoffer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("glimpse_tag", None), ("origin_choice", None), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("schooling_line", None), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("enemy_reason", None), _connector="OR"),
                    models.Q(
                        ("glimpse_tag", None),
                        ("appearance_section", None),
                        _connector="OR",
                    ),
                    models.Q(("glimpse_tag", None), ("beat", None), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("unlocked_by", None), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("prompt", ""), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(("glimpse_tag", None), ("feature_rows", False), _connector="OR"),
                    models.Q(
                        ("origin_choice", None),
                        ("schooling_line", None),
                        _connector="OR",
                    ),
                    models.Q(("origin_choice", None), ("enemy_reason", None), _connector="OR"),
                    models.Q(
                        ("origin_choice", None),
                        ("appearance_section", None),
                        _connector="OR",
                    ),
                    models.Q(("origin_choice", None), ("beat", None), _connector="OR"),
                    models.Q(("origin_choice", None), ("unlocked_by", None), _connector="OR"),
                    models.Q(("origin_choice", None), ("prompt", ""), _connector="OR"),
                    models.Q(("origin_choice", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(
                        ("origin_choice", None),
                        ("feature_rows", False),
                        _connector="OR",
                    ),
                    models.Q(
                        ("schooling_line", None),
                        ("enemy_reason", None),
                        _connector="OR",
                    ),
                    models.Q(
                        ("schooling_line", None),
                        ("appearance_section", None),
                        _connector="OR",
                    ),
                    models.Q(("schooling_line", None), ("beat", None), _connector="OR"),
                    models.Q(("schooling_line", None), ("unlocked_by", None), _connector="OR"),
                    models.Q(("schooling_line", None), ("prompt", ""), _connector="OR"),
                    models.Q(("schooling_line", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(
                        ("schooling_line", None),
                        ("feature_rows", False),
                        _connector="OR",
                    ),
                    models.Q(
                        ("enemy_reason", None),
                        ("appearance_section", None),
                        _connector="OR",
                    ),
                    models.Q(("enemy_reason", None), ("beat", None), _connector="OR"),
                    models.Q(("enemy_reason", None), ("unlocked_by", None), _connector="OR"),
                    models.Q(("enemy_reason", None), ("prompt", ""), _connector="OR"),
                    models.Q(("enemy_reason", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(("enemy_reason", None), ("feature_rows", False), _connector="OR"),
                    models.Q(("appearance_section", None), ("beat", None), _connector="OR"),
                    models.Q(
                        ("appearance_section", None),
                        ("unlocked_by", None),
                        _connector="OR",
                    ),
                    models.Q(("appearance_section", None), ("prompt", ""), _connector="OR"),
                    models.Q(
                        ("appearance_section", None),
                        ("enemy_degree", ""),
                        _connector="OR",
                    ),
                    models.Q(
                        ("appearance_section", None),
                        ("feature_rows", False),
                        _connector="OR",
                    ),
                    models.Q(("beat", None), ("unlocked_by", None), _connector="OR"),
                    models.Q(("beat", None), ("prompt", ""), _connector="OR"),
                    models.Q(("beat", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(("beat", None), ("feature_rows", False), _connector="OR"),
                    models.Q(("unlocked_by", None), ("prompt", ""), _connector="OR"),
                    models.Q(("unlocked_by", None), ("enemy_degree", ""), _connector="OR"),
                    models.Q(("unlocked_by", None), ("feature_rows", False), _connector="OR"),
                    models.Q(("prompt", ""), ("enemy_degree", ""), _connector="OR"),
                    models.Q(("prompt", ""), ("feature_rows", False), _connector="OR"),
                    models.Q(("enemy_degree", ""), ("feature_rows", False), _connector="OR"),
                ),
                name="distinctionoffer_at_most_one_opener",
            ),
        ),
    ]
