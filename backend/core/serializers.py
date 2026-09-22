import re
from decimal import Decimal

from rest_framework import serializers

from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    WaterBill,
    WaterBillItem,
    Zone,
)


class GreenhouseSerializer(serializers.ModelSerializer):
    areaM2 = serializers.DecimalField(
        source="area_m2", max_digits=10, decimal_places=2
    )
    zoneCount = serializers.SerializerMethodField()

    class Meta:
        model = Greenhouse
        fields = (
            "id",
            "name",
            "location",
            "areaM2",
            "notes",
            "zoneCount",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "zoneCount", "created_at", "updated_at")

    def get_zoneCount(self, obj):
        if hasattr(obj, "zone_count"):
            return obj.zone_count
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    zoneCode = serializers.CharField(source="zone_code")
    cropName = serializers.CharField(source="crop_name", allow_blank=True, required=False)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)

    class Meta:
        model = Zone
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "zoneCode",
            "cropName",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "greenhouseName", "created_at", "updated_at")

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        zone_code = attrs.get("zone_code") or getattr(self.instance, "zone_code", None)
        if greenhouse and zone_code:
            qs = Zone.objects.filter(greenhouse=greenhouse, zone_code=zone_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"zoneCode": "同一温室内分区编码必须唯一"}
                )
        return attrs


class ClimateLogSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    recordedAt = serializers.DateTimeField(source="recorded_at")
    tempC = serializers.DecimalField(source="temp_c", max_digits=5, decimal_places=2)
    humidityPct = serializers.DecimalField(
        source="humidity_pct", max_digits=5, decimal_places=2
    )
    parUmol = serializers.DecimalField(
        source="par_umol", max_digits=8, decimal_places=2, required=False
    )
    co2Ppm = serializers.DecimalField(
        source="co2_ppm", max_digits=8, decimal_places=2, required=False
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = ClimateLog
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "recordedAt",
            "tempC",
            "humidityPct",
            "parUmol",
            "co2Ppm",
            "created_at",
        )
        read_only_fields = ("id", "zoneCode", "greenhouseName", "created_at")

    def validate_humidityPct(self, value):
        if value < 20 or value > 100:
            raise serializers.ValidationError("湿度须在 20～100 之间")
        return value


class IrrigationCycleSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    startAt = serializers.DateTimeField(source="start_at")
    durationMin = serializers.IntegerField(source="duration_min")
    waterLiters = serializers.DecimalField(
        source="water_liters", max_digits=10, decimal_places=2
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )
    greenhouseId = serializers.IntegerField(source="zone.greenhouse_id", read_only=True)
    billItemId = serializers.SerializerMethodField()

    class Meta:
        model = IrrigationCycle
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseId",
            "greenhouseName",
            "billItemId",
            "startAt",
            "durationMin",
            "waterLiters",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "greenhouseId",
            "billItemId",
            "created_at",
            "updated_at",
        )

    def get_billItemId(self, obj):
        try:
            return obj.bill_item.id
        except WaterBillItem.DoesNotExist:
            return None


PERIOD_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class WaterBillItemSerializer(serializers.ModelSerializer):
    irrigationCycleId = serializers.PrimaryKeyRelatedField(
        source="irrigation_cycle", queryset=IrrigationCycle.objects.all()
    )
    zoneCode = serializers.CharField(
        source="irrigation_cycle.zone.zone_code", read_only=True
    )
    startAt = serializers.DateTimeField(
        source="irrigation_cycle.start_at", read_only=True
    )
    waterLiters = serializers.DecimalField(
        source="irrigation_cycle.water_liters",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    status = serializers.CharField(source="irrigation_cycle.status", read_only=True)

    class Meta:
        model = WaterBillItem
        fields = (
            "id",
            "irrigationCycleId",
            "zoneCode",
            "startAt",
            "waterLiters",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class WaterBillSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    periodMonth = serializers.CharField(source="period_month")
    pricePerLiter = serializers.DecimalField(
        source="price_per_liter", max_digits=10, decimal_places=4
    )
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)
    itemCount = serializers.SerializerMethodField()
    totalLiters = serializers.SerializerMethodField()
    totalFee = serializers.SerializerMethodField()
    items = WaterBillItemSerializer(many=True, read_only=True)

    class Meta:
        model = WaterBill
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "periodMonth",
            "pricePerLiter",
            "closedAt",
            "itemCount",
            "totalLiters",
            "totalFee",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "closedAt", "created_at", "updated_at")

    def validate_periodMonth(self, value):
        if not PERIOD_MONTH_RE.match(value):
            raise serializers.ValidationError("账期月格式须为 YYYY-MM，例如 2026-09")
        return value

    def validate_pricePerLiter(self, value):
        if value < 0:
            raise serializers.ValidationError("每升单价不能为负")
        return value

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(
            self.instance, "greenhouse", None
        )
        period_month = attrs.get("period_month") or getattr(
            self.instance, "period_month", None
        )
        if self.instance and "greenhouse" in attrs:
            has_foreign_item = WaterBillItem.objects.filter(
                bill=self.instance
            ).exclude(irrigation_cycle__zone__greenhouse=greenhouse).exists()
            if has_foreign_item:
                raise serializers.ValidationError(
                    {"greenhouseId": "账单已有其他温室的轮灌明细，不能改挂其他温室"}
                )
        if greenhouse and period_month:
            qs = WaterBill.objects.filter(
                greenhouse=greenhouse, period_month=period_month
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"periodMonth": "同一温室同一账期月只能有一张分摊单"}
                )
        return attrs

    def get_itemCount(self, obj):
        return len(obj.items.all())

    def _totals(self, obj):
        if hasattr(obj, "_total_liters"):
            total_liters = obj._total_liters
        else:
            total_liters = obj.total_liters()
        total_fee = (total_liters * obj.price_per_liter).quantize(Decimal("0.01"))
        return total_liters, total_fee

    def get_totalLiters(self, obj):
        return self._totals(obj)[0]

    def get_totalFee(self, obj):
        return self._totals(obj)[1]
