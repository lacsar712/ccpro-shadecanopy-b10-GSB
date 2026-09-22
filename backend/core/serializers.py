from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from rest_framework import serializers

from .models import (
    BILLING_MONTH_VALIDATOR,
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    WaterShareBill,
    WaterShareEntry,
    Zone,
)

CENT = Decimal("0.01")


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

    class Meta:
        model = IrrigationCycle
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
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
            "created_at",
            "updated_at",
        )


def bill_total_fee(bill, total_liters=None):
    """总费用 = 总升数 × 每升单价，四舍五入到分（误差 ≤ 0.01）。"""
    if total_liters is None:
        total_liters = getattr(bill, "total_liters", None)
    if total_liters is None:
        total_liters = bill.total_water_liters()
    return (Decimal(total_liters) * bill.price_per_liter).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


class WaterShareEntrySerializer(serializers.ModelSerializer):
    billId = serializers.PrimaryKeyRelatedField(
        source="bill", queryset=WaterShareBill.objects.all()
    )
    cycleId = serializers.PrimaryKeyRelatedField(
        source="cycle", queryset=IrrigationCycle.objects.all()
    )
    zoneId = serializers.IntegerField(source="cycle.zone_id", read_only=True)
    zoneCode = serializers.CharField(source="cycle.zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="cycle.zone.greenhouse.name", read_only=True
    )
    startAt = serializers.DateTimeField(source="cycle.start_at", read_only=True)
    waterLiters = serializers.DecimalField(
        source="cycle.water_liters",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    cycleStatus = serializers.CharField(source="cycle.status", read_only=True)

    class Meta:
        model = WaterShareEntry
        fields = (
            "id",
            "billId",
            "cycleId",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "startAt",
            "waterLiters",
            "cycleStatus",
            "created_at",
        )
        read_only_fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "startAt",
            "waterLiters",
            "cycleStatus",
            "created_at",
        )

    def validate(self, attrs):
        bill = attrs.get("bill") or getattr(self.instance, "bill", None)
        cycle = attrs.get("cycle") or getattr(self.instance, "cycle", None)
        if bill and cycle:
            if cycle.zone.greenhouse_id != bill.greenhouse_id:
                raise serializers.ValidationError(
                    {"cycleId": "轮灌所属分区必须属于该温室"}
                )
            qs = WaterShareEntry.objects.filter(cycle=cycle)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"cycleId": "该轮灌已挂在一张分摊单上，不能重复挂载"}
                )
        return attrs


class WaterShareBillSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)
    billingMonth = serializers.CharField(
        source="billing_month", validators=[BILLING_MONTH_VALIDATOR]
    )
    pricePerLiter = serializers.DecimalField(
        source="price_per_liter",
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(0)],
    )
    sealedAt = serializers.DateTimeField(source="sealed_at", read_only=True)
    sealed = serializers.SerializerMethodField()
    entryCount = serializers.SerializerMethodField()
    totalLiters = serializers.SerializerMethodField()
    totalFee = serializers.SerializerMethodField()
    entries = WaterShareEntrySerializer(many=True, read_only=True)

    class Meta:
        model = WaterShareBill
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "billingMonth",
            "pricePerLiter",
            "sealed",
            "sealedAt",
            "entryCount",
            "totalLiters",
            "totalFee",
            "entries",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "greenhouseName",
            "sealed",
            "sealedAt",
            "entryCount",
            "totalLiters",
            "totalFee",
            "entries",
            "created_at",
            "updated_at",
        )

    def _total_liters(self, obj):
        annotated = getattr(obj, "total_liters", None)
        if annotated is not None:
            return Decimal(annotated)
        return obj.total_water_liters()

    def get_sealed(self, obj):
        return obj.is_sealed

    def get_entryCount(self, obj):
        annotated = getattr(obj, "entry_count", None)
        if annotated is not None:
            return annotated
        return obj.entries.count()

    def get_totalLiters(self, obj):
        return str(self._total_liters(obj).quantize(CENT, rounding=ROUND_HALF_UP))

    def get_totalFee(self, obj):
        return str(bill_total_fee(obj, self._total_liters(obj)))

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        billing_month = attrs.get("billing_month") or getattr(
            self.instance, "billing_month", None
        )
        if greenhouse and billing_month:
            qs = WaterShareBill.objects.filter(
                greenhouse=greenhouse, billing_month=billing_month
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"billingMonth": "同一温室同一账期月只能有一张分摊单"}
                )
        return attrs
