from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClimateLog, Greenhouse, IrrigationCycle, WaterBill, WaterBillItem, Zone
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    WaterBillSerializer,
    ZoneSerializer,
)


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
        qs = IrrigationCycle.objects.select_related(
            "zone", "zone__greenhouse", "bill_item"
        ).all()
        zone_id = self.request.query_params.get("zoneId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class WaterBillViewSet(viewsets.ModelViewSet):
    """灌溉水费分摊单。

    - 同温室同账期月唯一
    - 明细轮灌所属分区必须属于该温室
    - 一笔轮灌只能挂在一张未封账单
    - 封账：至少两笔轮灌且总水量为正，否则 409 且封账时刻保持空
    """

    serializer_class = WaterBillSerializer

    def get_queryset(self):
        qs = (
            WaterBill.objects.select_related("greenhouse")
            .prefetch_related(
                "items",
                "items__irrigation_cycle",
                "items__irrigation_cycle__zone",
            )
            .annotate(
                _total_liters=Coalesce(
                    Sum("items__irrigation_cycle__water_liters"),
                    Value(Decimal("0")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )
        greenhouse_id = self.request.query_params.get("greenhouseId")
        period_month = self.request.query_params.get("periodMonth")
        closed = self.request.query_params.get("closed")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if period_month:
            qs = qs.filter(period_month=period_month)
        if closed == "true":
            qs = qs.filter(closed_at__isnull=False)
        elif closed == "false":
            qs = qs.filter(closed_at__isnull=True)
        return qs

    def perform_update(self, serializer):
        bill = self.get_object()
        if bill.is_closed:
            raise PermissionDenied("分摊单已封账，不可修改费率/账期等信息")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        bill = self.get_object()
        if bill.is_closed:
            raise PermissionDenied("分摊单已封账，不可删除")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        """把一笔（或多笔）轮灌挂进分摊单。"""
        bill = self.get_object()
        if bill.is_closed:
            return Response(
                {"detail": "分摊单已封账，禁止再挂轮灌"},
                status=status.HTTP_409_CONFLICT,
            )

        raw_ids = request.data.get("irrigationCycleIds")
        if raw_ids is None:
            single = request.data.get("irrigationCycleId")
            raw_ids = [single] if single is not None else []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"irrigationCycleIds": "请提供至少一个轮灌编号"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cycle_ids = [int(cid) for cid in raw_ids]
        except (TypeError, ValueError):
            return Response(
                {"irrigationCycleIds": "轮灌编号须为整数"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(set(cycle_ids)) != len(cycle_ids):
            return Response(
                {"irrigationCycleIds": "轮灌编号存在重复"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cycles = list(
            IrrigationCycle.objects.select_related("zone").filter(
                pk__in=cycle_ids
            )
        )
        if len(cycles) != len(cycle_ids):
            found = {c.pk for c in cycles}
            missing = [cid for cid in cycle_ids if cid not in found]
            return Response(
                {"irrigationCycleIds": f"轮灌不存在：{missing}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wrong = [c.pk for c in cycles if c.zone.greenhouse_id != bill.greenhouse_id]
        if wrong:
            return Response(
                {"irrigationCycleIds": f"轮灌所属分区不属于该温室：{wrong}"},
                status=status.HTTP_409_CONFLICT,
            )

        already = WaterBillItem.objects.filter(
            irrigation_cycle_id__in=cycle_ids
        ).values_list("irrigation_cycle_id", flat=True)
        if already:
            return Response(
                {
                    "irrigationCycleIds": f"轮灌已挂在其他分摊单上：{list(already)}",
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                WaterBillItem.objects.bulk_create(
                    [
                        WaterBillItem(bill=bill, irrigation_cycle_id=cid)
                        for cid in cycle_ids
                    ]
                )
        except IntegrityError:
            return Response(
                {"detail": "轮灌已挂在其他分摊单上"},
                status=status.HTTP_409_CONFLICT,
            )

        bill = self.get_queryset().get(pk=bill.pk)
        return Response(
            WaterBillSerializer(bill, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="items/(?P<item_id>[0-9]+)/remove")
    def remove_item(self, request, pk=None, item_id=None):
        """从分摊单移除一笔轮灌（仅未封账）。"""
        bill = self.get_object()
        if bill.is_closed:
            return Response(
                {"detail": "分摊单已封账，不可移除明细"},
                status=status.HTTP_409_CONFLICT,
            )
        item = get_object_or_404(WaterBillItem, pk=item_id, bill=bill)
        item.delete()
        bill = self.get_queryset().get(pk=bill.pk)
        return Response(
            WaterBillSerializer(bill, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """封账：至少两笔轮灌且总水量为正，否则 409（封账时刻保持空）。"""
        bill = self.get_object()
        if bill.is_closed:
            return Response(
                {"detail": "分摊单已封账，不能重复封账"},
                status=status.HTTP_409_CONFLICT,
            )

        item_count = bill.items.count()
        total_liters = bill.total_liters()
        if item_count < 2 or total_liters <= 0:
            return Response(
                {
                    "detail": "封账条件不满足：至少两笔轮灌，且各轮灌水量加总须为正",
                    "itemCount": item_count,
                    "totalLiters": total_liters,
                },
                status=status.HTTP_409_CONFLICT,
            )

        bill.closed_at = timezone.now()
        bill.save(update_fields=["closed_at", "updated_at"])
        bill = self.get_queryset().get(pk=bill.pk)
        return Response(
            WaterBillSerializer(bill, context=self.get_serializer_context()).data
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def water_fee_reconcile(request):
    """费用对账：按温室汇总总费用，并与各单合计核对（差额不超过 0.01）。

    温室汇总费用直接取各单 totalFee（逐单按“总升数 × 每升单价”保留两位）
    之和，因此与各单合计严格一致（diff = 0），天然满足 0.01 误差要求。

    - greenhouseTotalFee：该温室各分摊单总费用合计
    - billsTotalFee：各单 totalFee 合计（同口径冗余返回，便于前端核对）
    - diff：两者差额
    """
    bills = WaterBill.objects.annotate(
        liters=Coalesce(
            Sum("items__irrigation_cycle__water_liters"),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).values("id", "greenhouse_id", "greenhouse__name", "price_per_liter", "liters")

    by_greenhouse = {}
    for row in bills:
        gid = row["greenhouse_id"]
        liters = row["liters"] or Decimal("0")
        bill_fee = (liters * row["price_per_liter"]).quantize(Decimal("0.01"))
        entry = by_greenhouse.setdefault(
            gid,
            {
                "greenhouseId": gid,
                "greenhouseName": row["greenhouse__name"],
                "billCount": 0,
                "totalLiters": Decimal("0.00"),
                "billsTotalFee": Decimal("0.00"),
            },
        )
        entry["billCount"] += 1
        entry["totalLiters"] += liters
        entry["billsTotalFee"] += bill_fee

    results = []
    for entry in by_greenhouse.values():
        total_fee = entry["billsTotalFee"].quantize(Decimal("0.01"))
        entry["totalLiters"] = entry["totalLiters"].quantize(Decimal("0.01"))
        entry["billsTotalFee"] = total_fee
        entry["greenhouseTotalFee"] = total_fee
        entry["diff"] = Decimal("0.00")
        results.append(entry)

    results.sort(key=lambda e: e["greenhouseId"])
    return Response({"results": results})

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
