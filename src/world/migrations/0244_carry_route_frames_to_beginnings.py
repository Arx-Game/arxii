# #4395: the frame prose every character of a beginning shares lived on the beginning's one
# route row (OriginTemplate.frame_narrative, the retired "Upbringing" pick). It moves onto the
# beginning itself (Beginnings.frame), where the Origin pick shows it. Data only: the column
# arrived in 0243 (ADR-0237 restructure: nothing authored is dropped; the route keeps its copy).

from django.db import migrations


def carry_frames(apps, schema_editor):
    Beginnings = apps.get_model("arxii", "Beginnings")
    OriginTemplate = apps.get_model("arxii", "OriginTemplate")
    for beginning in Beginnings.objects.filter(frame=""):
        route = (
            OriginTemplate.objects.filter(beginning=beginning)
            .exclude(frame_narrative="")
            .order_by("-is_active", "sort_order", "id")
            .first()
        )
        if route is None:
            continue
        beginning.frame = route.frame_narrative
        beginning.save(update_fields=["frame"])


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0243_beginning_frame_station_strikes_and_beat_age_picks"),
    ]

    operations = [
        migrations.RunPython(carry_frames, migrations.RunPython.noop),
    ]
