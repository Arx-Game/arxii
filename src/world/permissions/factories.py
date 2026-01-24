"""Factory classes for permissions models."""

import factory
from factory.django import DjangoModelFactory

from world.permissions.models import PermissionGroup, PermissionGroupMember


class PermissionGroupFactory(DjangoModelFactory):
    """Factory for creating PermissionGroup instances."""

    class Meta:
        model = PermissionGroup

    owner = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    name = factory.Sequence(lambda n: f"Group {n}")


class PermissionGroupMemberFactory(DjangoModelFactory):
    """Factory for creating PermissionGroupMember instances."""

    class Meta:
        model = PermissionGroupMember

    group = factory.SubFactory(PermissionGroupFactory)
    tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
