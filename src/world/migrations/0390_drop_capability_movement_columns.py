# Contract step of #5066: the capability row no longer says how a power moves or dodges.
#
# ADR-0237 disposition for these three authored-content columns: empty in production
# (verified at PR review by a maintainer; no repo seed sets them). Applications now carry
# the way of moving and the dodge (0387); nothing is copied across.
#
# Also drops CombatPull.resonance and SceneActionPullDeclaration.resonance (play state,
# resettable per ADR-0237): a pull may now mix resonances, each thread paid from its own
# (maintainer ruling 2026-11-11), so the column says nothing the threads do not. A pull's
# burn names its resonance in CombatPull.burned_resonance and
# SceneActionPullDeclaration.burn_resonance (0387). A pending scene pull with a burn loses
# which resonance burns; such a pull was of one resonance under the old rule, and a pull of
# one resonance burns that one without naming it, so nothing is carried.
#
# Deploy window: between `migrate` and the reload, the old process still reads
# `resonance_id` on these two tables, so a thread pull declared in those seconds fails.
# Play state only; accepted with the capability-column window above. Forward-only in
# practice: reversing re-adds both columns NOT NULL with no default, which fails if either
# table has rows.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0389_movement_powers_through_applications"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="capabilitytype",
            name="reaction_cost_kind",
        ),
        migrations.RemoveField(
            model_name="capabilitytype",
            name="reaction_reach",
        ),
        migrations.RemoveField(
            model_name="capabilitytype",
            name="traversal",
        ),
        migrations.RemoveField(
            model_name="combatpull",
            name="resonance",
        ),
        migrations.RemoveField(
            model_name="sceneactionpulldeclaration",
            name="resonance",
        ),
    ]
