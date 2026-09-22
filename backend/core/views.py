from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    WaterShareBill,
    WaterShareEntry,
    Zone,
)
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    WaterShareBillSerializer,
    WaterShareEntrySerializer,
    ZoneSerializer,
    bill_total_fee,
)

CENT = Decimal("0.01")


class GreenhouseViewSet(viewsets.ModelViewSet):
    queryset = Greenhouse.objects.annotate(zone_count=Count("zones")).all()
    serializer_class = GreenhouseSerializer


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = Zone.objects.select_related("greenhouse").all()
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class ClimateLogViewSet(viewsets.ModelViewSet):
    serializer_class = ClimateLogSerializer

    def get_queryset(self):
        qs = ClimateLog.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class IrrigationCycleViewSet(viewsets.ModelViewSet):
    serializer_class = IrrigationCycleSerializer

    def get_queryset(self):
        qs = IrrigationCycle.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if greenhouse_id:
            qs = qs.filter(zone__greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


def _conflict(message):
    return Response({"detail": message}, status=status.HTTP_409_CONFLICT)


class WaterShareBillViewSet(viewsets.ModelViewSet):
    """灌溉水费分摊单：同温室同账期月唯一；封账后只读且禁止再挂轮灌。"""

    serializer_class = WaterShareBillSerializer

    def get_queryset(self):
        qs = (
            WaterShareBill.objects.select_related("greenhouse")
            .prefetch_related("entries__cycle__zone__greenhouse")
            .annotate(
                entry_count=Count("entries"),
                total_liters=Coalesce(
                    Sum("entries__cycle__water_liters"),
                    Decimal("0"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
            )
            .order_by("-billing_month", "id")
        )
        params = self.request.query_params
        greenhouse_id = params.get("greenhouseId")
        billing_month = params.get("billingMonth")
        sealed = params.get("sealed")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if billing_month:
            qs = qs.filter(billing_month=billing_month)
        if sealed in ("true", "false"):
            qs = qs.filter(sealed_at__isnull=(sealed == "false"))
        return qs

    def _reject_if_sealed(self, instance):
        if instance.is_sealed:
            return _conflict("分摊单已封账，禁止修改")
        return None

    def update(self, request, *args, **kwargs):
        resp = self._reject_if_sealed(self.get_object())
        return resp or super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        resp = self._reject_if_sealed(self.get_object())
        return resp or super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        resp = self._reject_if_sealed(self.get_object())
        return resp or super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def seal(self, request, pk=None):
        """封账：至少两笔轮灌且水量加总为正，否则 409 且 sealed_at 保持空。"""
        bill = self.get_object()
        if bill.is_sealed:
            return _conflict("分摊单已封账")
        entry_count = bill.entries.count()
        if entry_count < 2:
            return _conflict("账单至少两笔轮灌才能封账")
        total_liters = bill.total_water_liters()
        if total_liters <= 0:
            return _conflict("各轮灌水量加总须为正才能封账")
        bill.sealed_at = timezone.now()
        bill.save(update_fields=["sealed_at", "updated_at"])
        bill = self.get_queryset().get(pk=bill.pk)
        serializer = self.get_serializer(bill)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def reconcile(self, request):
        """费用对账：按温室汇总总费用，与各单合计的差不超过 0.01。"""
        bills = self.get_queryset().order_by("greenhouse_id", "billing_month", "id")
        groups = {}
        for bill in bills:
            fee = bill_total_fee(bill, bill.total_liters)
            bucket = groups.setdefault(
                bill.greenhouse_id,
                {
                    "greenhouseId": bill.greenhouse_id,
                    "greenhouseName": bill.greenhouse.name,
                    "billCount": 0,
                    "totalLiters": Decimal("0"),
                    "totalFee": Decimal("0"),
                    "billFeeSum": Decimal("0"),
                },
            )
            bucket["billCount"] += 1
            bucket["totalLiters"] += Decimal(bill.total_liters)
            bucket["totalFee"] += fee
        # 第二遍按单据详情口径逐单重算合计，与汇总值对账
        for bill in bills:
            groups[bill.greenhouse_id]["billFeeSum"] += bill_total_fee(
                bill, bill.total_liters
            )
        results = []
        for bucket in groups.values():
            diff = abs(bucket["totalFee"] - bucket["billFeeSum"])
            results.append(
                {
                    "greenhouseId": bucket["greenhouseId"],
                    "greenhouseName": bucket["greenhouseName"],
                    "billCount": bucket["billCount"],
                    "totalLiters": str(
                        bucket["totalLiters"].quantize(CENT, rounding=ROUND_HALF_UP)
                    ),
                    "totalFee": str(
                        bucket["totalFee"].quantize(CENT, rounding=ROUND_HALF_UP)
                    ),
                    "billFeeSum": str(
                        bucket["billFeeSum"].quantize(CENT, rounding=ROUND_HALF_UP)
                    ),
                    "diff": str(diff.quantize(CENT, rounding=ROUND_HALF_UP)),
                }
            )
        return Response({"results": results})


class WaterShareEntryViewSet(viewsets.ModelViewSet):
    """分摊明细：把轮灌挂入未封账的分摊单；封账后禁止再挂/再拆。"""

    serializer_class = WaterShareEntrySerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        qs = WaterShareEntry.objects.select_related(
            "bill", "cycle__zone__greenhouse"
        ).all()
        bill_id = self.request.query_params.get("billId")
        if bill_id:
            qs = qs.filter(bill_id=bill_id)
        return qs

    def create(self, request, *args, **kwargs):
        bill_id = request.data.get("billId")
        bill = WaterShareBill.objects.filter(pk=bill_id).first()
        if bill is not None and bill.is_sealed:
            return _conflict("分摊单已封账，禁止再挂轮灌")
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        entry = self.get_object()
        if entry.bill.is_sealed:
            return _conflict("分摊单已封账，禁止移除轮灌")
        return super().destroy(request, *args, **kwargs)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
            start_at__gte=today_start,
            start_at__lt=today_end,
        ).count(),
    }
    return Response(data)
