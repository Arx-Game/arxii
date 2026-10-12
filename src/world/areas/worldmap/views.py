"""The staff world-map API (#4242): region maps on the world-builder router.

Reads: the region list, one region, its ``pips`` payload (terrain pips and the
footprints that touch it) and its latest uploaded ``file``. One write that is
not an action: the multipart ``upload``, which calls
``import_region_map_file`` the way the roster's media views call the image
host. Every other write (create a region, carve, paint) is a REGISTRY action.
Staff only: a build-grant holder's warrant covers rooms and areas, not the
world map.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from world.areas.worldmap.constants import PIPS_PER_CELL, Terrain
from world.areas.worldmap.models import RegionMap, RegionMapUpload
from world.areas.worldmap.services import (
    MAX_MAP_FILE_BYTES,
    WorldMapServiceError,
    import_region_map_file,
    region_read,
    upload_text,
)


class RegionMapUploadSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", default="")

    class Meta:
        model = RegionMapUpload
        fields = [
            "id",
            "file_name",
            "byte_size",
            "generator_version",
            "source_width_px",
            "source_height_px",
            "uploaded_by_name",
            "uploaded_at",
            "rasterized_at",
        ]
        read_only_fields = fields


class RegionMapSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", default="")
    pips_per_cell = serializers.SerializerMethodField()
    latest_upload = serializers.SerializerMethodField()

    class Meta:
        model = RegionMap
        fields = [
            "id",
            "name",
            "area",
            "area_name",
            "anchor_x",
            "anchor_y",
            "width_cells",
            "height_cells",
            "pips_per_cell",
            "created_at",
            "latest_upload",
        ]
        read_only_fields = fields

    def get_pips_per_cell(self, obj: RegionMap) -> int:
        return PIPS_PER_CELL

    def get_latest_upload(self, obj: RegionMap) -> dict[str, Any] | None:
        upload = obj.uploads.order_by("-uploaded_at").first()
        return RegionMapUploadSerializer(upload).data if upload is not None else None


class RegionMapFootprintSerializer(serializers.Serializer):
    area_id = serializers.IntegerField()
    name = serializers.CharField()
    level = serializers.IntegerField()
    level_display = serializers.CharField()
    parent_id = serializers.IntegerField(allow_null=True)
    realm_id = serializers.IntegerField(allow_null=True)
    holder_org_id = serializers.IntegerField(allow_null=True)
    holder_name = serializers.CharField(allow_blank=True)
    title_id = serializers.IntegerField(allow_null=True)
    seat = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    pips = serializers.ListField(child=serializers.ListField(child=serializers.IntegerField()))


class RegionMapPipsSerializer(serializers.Serializer):
    """The region-map view's payload: ``pips`` rows are ``[x, y, terrain, river]``."""

    region = RegionMapSerializer()
    terrains = serializers.ListField(child=serializers.CharField())
    pips = serializers.ListField(child=serializers.ListField())
    footprints = RegionMapFootprintSerializer(many=True)


class RegionMapUploadInputSerializer(serializers.Serializer):
    file = serializers.FileField(max_length=200, allow_empty_file=False)

    def validate_file(self, value: Any) -> Any:
        if value.size > MAX_MAP_FILE_BYTES:
            msg = "That file is larger than a map file can be."
            raise serializers.ValidationError(msg)
        return value


class RegionMapUploadResultSerializer(serializers.Serializer):
    upload = RegionMapUploadSerializer()
    pip_count = serializers.IntegerField()
    region = RegionMapSerializer()


@extend_schema(tags=["world-builder"])
class RegionMapViewSet(viewsets.ReadOnlyModelViewSet):
    """Region maps for the Atlas (#4242). Staff only."""

    serializer_class = RegionMapSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = RegionMap.objects.select_related("area").order_by("name")
    filterset_fields = ["area"]
    pagination_class = None

    @extend_schema(responses={200: RegionMapPipsSerializer})
    @action(detail=True, methods=["get"], url_path="pips")
    def pips(self, request: Request, pk: str | None = None) -> Response:
        region = self.get_object()
        read = region_read(region)
        payload = {
            "region": RegionMapSerializer(region).data,
            "terrains": list(Terrain.values),
            "pips": [[x, y, terrain, river] for (x, y, terrain, river) in read.pips],
            "footprints": [
                RegionMapFootprintSerializer(
                    {
                        "area_id": f.area_id,
                        "name": f.name,
                        "level": f.level,
                        "level_display": f.level_display,
                        "parent_id": f.parent_id,
                        "realm_id": f.realm_id,
                        "holder_org_id": f.holder_org_id,
                        "holder_name": f.holder_name,
                        "title_id": f.title_id,
                        "seat": list(f.seat) if f.seat is not None else None,
                        "pips": [list(p) for p in f.pips],
                    }
                ).data
                for f in read.footprints
            ],
        }
        return Response(payload)

    @extend_schema(
        request=RegionMapUploadInputSerializer,
        responses={201: RegionMapUploadResultSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="upload",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload(self, request: Request, pk: str | None = None) -> Response:
        region = self.get_object()
        serializer = RegionMapUploadInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data["file"]
        try:
            upload = import_region_map_file(
                region=region, file_name=file.name, data=file.read(), actor=request.user
            )
        except WorldMapServiceError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        region.refresh_from_db()
        return Response(
            {
                "upload": RegionMapUploadSerializer(upload).data,
                "pip_count": region.pips.count(),
                "region": RegionMapSerializer(region).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request: Request, pk: str | None = None) -> HttpResponse:
        region = self.get_object()
        upload = region.uploads.order_by("-uploaded_at").first()
        if upload is None:
            return Response(
                {"detail": "No file has been uploaded."}, status=status.HTTP_404_NOT_FOUND
            )
        response = HttpResponse(upload_text(upload), content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{upload.file_name}"'
        return response
