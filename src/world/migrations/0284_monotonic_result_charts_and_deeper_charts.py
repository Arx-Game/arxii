"""Make the result charts monotonic and add the two deeper charts (#4593, #4551).

Data only. Two parts, both computed against the real rows (the newest production dump
held exactly the seeded values, so the repair touches charts -4 and -2):

1. The smallest repair to every chart whose "Partial Success or better" chance is below
   the neighbouring harder chart's: the Failure / Partial Success boundary moves so the
   two chances are equal. Nothing else on the chart changes, and charts -6 and -5 are
   never touched (they have no harder chart to fall below, and -5 already leads).
2. Adds chart -7 ("Failure -7": Critical Failure, Failure and a small Partial Success,
   no Success) and chart -8 ("Impossible": Critical Failure and Failure only). The names
   are placeholders for the owner to author; the odds are example rows.

A database with no result charts (a fresh one) is left alone: the seed creates them.
Reversing removes charts -7 and -8; the boundary repair is harmless and stays.
"""

from django.db import migrations

CRITICAL_FAILURE = "Critical Failure"
FAILURE = "Failure"
PARTIAL_SUCCESS = "Partial Success"

# (rank_difference, name, ((outcome name, min_roll, max_roll), ...))
NEW_CHARTS = (
    (
        -7,
        "Failure -7",
        ((CRITICAL_FAILURE, 1, 15), (FAILURE, 16, 95), (PARTIAL_SUCCESS, 96, 100)),
    ),
    (-8, "Impossible", ((CRITICAL_FAILURE, 1, 20), (FAILURE, 21, 100))),
)
FIRST_REPAIRABLE_DIFFERENCE = -5


def _partial_or_better(rows):
    return sum(r.max_roll - r.min_roll + 1 for r in rows if r.outcome.success_level >= 0)


def repair_partial_success_chances(apps, schema_editor):
    ResultChartOutcome = apps.get_model("arxii", "ResultChartOutcome")
    by_chart = {}
    for row in ResultChartOutcome.objects.select_related("chart", "outcome"):
        by_chart.setdefault(row.chart.rank_difference, []).append(row)

    previous_chance = None
    for rank_difference in sorted(by_chart):
        rows = by_chart[rank_difference]
        chance = _partial_or_better(rows)
        if (
            previous_chance is not None
            and rank_difference > FIRST_REPAIRABLE_DIFFERENCE
            and chance < previous_chance
        ):
            failure = next((r for r in rows if r.outcome.name == FAILURE), None)
            partial = next((r for r in rows if r.outcome.name == PARTIAL_SUCCESS), None)
            if failure is None or partial is None or failure.max_roll + 1 != partial.min_roll:
                previous_chance = chance
                continue
            shift = previous_chance - chance
            if shift >= failure.max_roll - failure.min_roll + 1:
                previous_chance = chance
                continue
            failure.max_roll -= shift
            partial.min_roll -= shift
            failure.save(update_fields=["max_roll"])
            partial.save(update_fields=["min_roll"])
            chance = previous_chance
        previous_chance = chance


def add_deeper_charts(apps, schema_editor):
    ResultChart = apps.get_model("arxii", "ResultChart")
    ResultChartOutcome = apps.get_model("arxii", "ResultChartOutcome")
    CheckOutcome = apps.get_model("arxii", "CheckOutcome")
    if not ResultChart.objects.exists():
        return
    outcomes = {
        o.name: o
        for o in CheckOutcome.objects.filter(name__in=(CRITICAL_FAILURE, FAILURE, PARTIAL_SUCCESS))
    }
    if len(outcomes) != 3:
        return
    for rank_difference, name, bands in NEW_CHARTS:
        chart, created = ResultChart.objects.get_or_create(
            rank_difference=rank_difference, defaults={"name": name}
        )
        if not created:
            continue
        ResultChartOutcome.objects.bulk_create(
            [
                ResultChartOutcome(
                    chart=chart, outcome=outcomes[outcome_name], min_roll=low, max_roll=high
                )
                for outcome_name, low, high in bands
            ]
        )


def remove_deeper_charts(apps, schema_editor):
    ResultChart = apps.get_model("arxii", "ResultChart")
    # Only the placeholder-named rows this migration made: a chart the owner has since
    # renamed or authored at these ranks is left alone.
    for rank_difference, name, _bands in NEW_CHARTS:
        ResultChart.objects.filter(rank_difference=rank_difference, name=name).delete()


def forwards(apps, schema_editor):
    repair_partial_success_chances(apps, schema_editor)
    add_deeper_charts(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0283_condition_template_reaction_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, remove_deeper_charts),
    ]
