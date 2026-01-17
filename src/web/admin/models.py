"""Models for custom admin functionality."""

from django.db import models


class AdminPinnedModelManager(models.Manager):
    """Manager with natural key support for AdminPinnedModel."""

    def get_by_natural_key(self, app_label: str, model_name: str):
        return self.get(app_label=app_label, model_name=model_name)


class AdminPinnedModel(models.Model):
    """
    Tracks which models appear in the 'Recent' section of admin sidebar.

    Manually configured by staff via 'Pin to Recent' button.
    """

    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AdminPinnedModelManager()

    class Meta:
        ordering = ["sort_order", "created_at"]
        unique_together = [["app_label", "model_name"]]
        verbose_name = "Pinned Admin Model"
        verbose_name_plural = "Pinned Admin Models"

    def __str__(self):
        return f"{self.app_label}.{self.model_name}"

    def natural_key(self) -> tuple[str, str]:
        return (self.app_label, self.model_name)


class AdminExcludedModelManager(models.Manager):
    """Manager with natural key support for AdminExcludedModel."""

    def get_by_natural_key(self, app_label: str, model_name: str):
        return self.get(app_label=app_label, model_name=model_name)


class AdminExcludedModel(models.Model):
    """
    Models excluded from configuration export.

    Uses blocklist approach: models NOT in this table are exportable.
    New models are automatically exportable without code changes.
    """

    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AdminExcludedModelManager()

    class Meta:
        unique_together = [["app_label", "model_name"]]
        verbose_name = "Excluded Export Model"
        verbose_name_plural = "Excluded Export Models"

    def __str__(self):
        return f"{self.app_label}.{self.model_name}"

    def natural_key(self) -> tuple[str, str]:
        return (self.app_label, self.model_name)
