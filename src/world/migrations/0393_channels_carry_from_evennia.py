"""Player channels (#3299): move off Evennia's ChannelDB onto world.channels.

Data only (no schema operation; 0392 made the tables).

Forward:
1. The PUBLIC channel exists (the replacement for Evennia's stock "Public" channel).
2. Every non-covert Organization without an ORG channel gets one (the replacement for
   the Evennia ``house_<pk>`` channels, and the channel every org is provisioned with
   from now on). Naming mirrors ``world.channels.services.provision_org_channel``: the
   org name cut to 80, " (org)" on a clash or on the reserved public name, then
   " (org <pk>)". Repeated here because a migration must not import live services.
3. Evennia ChannelDB rows keyed "Public" or "house_<anything>" are deleted, with the
   Attributes they owned (Evennia's pre_delete signal does that for live models; the
   historical model has no signal). Subscription and Tag through-rows go with the
   channel. MudInfo and every other ChannelDB row are untouched.

Reverse: noop. The deleted Evennia channels are not rebuilt (DEFAULT_CHANNELS is now
empty, so nothing would recreate or use them), and the created channels are left for
0392's reverse, which drops their tables.
"""

# seed-data-ok: carries rows the database already holds into the new store - the
# Evennia Public channel and each house_<pk> channel become world.channels rows, and
# each existing non-covert Organization gets the ORG channel every org is now made with.
# Nothing authored is invented; the only text written is the public channel's fixed
# description, identical to ensure_public_channel's.

from django.db import migrations

PUBLIC_CHANNEL_NAME = "Public"
PUBLIC_CHANNEL_DESCRIPTION = (
    "The game-wide out-of-character channel. Everyone can read and post here."
)
KIND_PUBLIC = "public"
KIND_ORG = "org"
CHANNEL_NAME_MAX = 80
ORG_NAME_SUFFIX = " (org)"


def _org_channel_name(channel_model, organization) -> str:
    name = organization.name[:CHANNEL_NAME_MAX]
    if name == PUBLIC_CHANNEL_NAME or channel_model.objects.filter(name=name).exists():
        name = organization.name[: CHANNEL_NAME_MAX - len(ORG_NAME_SUFFIX)] + ORG_NAME_SUFFIX
        if channel_model.objects.filter(name=name).exists():
            suffix = f" (org {organization.pk})"
            name = organization.name[: CHANNEL_NAME_MAX - len(suffix)] + suffix
    return name


def carry_channels_off_evennia(apps, schema_editor):
    Channel = apps.get_model("arxii", "Channel")
    Organization = apps.get_model("arxii", "Organization")
    ChannelDB = apps.get_model("comms", "ChannelDB")
    Attribute = apps.get_model("typeclasses", "Attribute")

    if not Channel.objects.filter(name=PUBLIC_CHANNEL_NAME).exists():
        Channel.objects.create(
            name=PUBLIC_CHANNEL_NAME,
            kind=KIND_PUBLIC,
            description=PUBLIC_CHANNEL_DESCRIPTION,
        )

    has_channel = set(
        Channel.objects.filter(organization__isnull=False).values_list("organization_id", flat=True)
    )
    for organization in Organization.objects.filter(is_covert=False).order_by("pk"):
        if organization.pk in has_channel:
            continue
        Channel.objects.create(
            name=_org_channel_name(Channel, organization),
            kind=KIND_ORG,
            organization=organization,
        )

    retired = ChannelDB.objects.filter(
        db_key__iexact=PUBLIC_CHANNEL_NAME
    ) | ChannelDB.objects.filter(db_key__startswith="house_")
    retired_ids = list(retired.values_list("pk", flat=True))
    if not retired_ids:
        return
    attribute_ids = list(
        ChannelDB.db_attributes.through.objects.filter(channeldb_id__in=retired_ids).values_list(
            "attribute_id", flat=True
        )
    )
    ChannelDB.objects.filter(pk__in=retired_ids).delete()
    Attribute.objects.filter(pk__in=attribute_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0392_channel_channelban_channelmessage_and_more"),
        ("comms", "0022_defaultchannel_alter_channeldb_id_alter_msg_id_and_more"),
        ("typeclasses", "0017_use_index_instead_of_index_together_in_tags"),
    ]

    operations = [
        migrations.RunPython(carry_channels_off_evennia, migrations.RunPython.noop),
    ]
