from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce


class Greenhouse(models.Model):
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, blank=True, default="")
    area_m2 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Zone(models.Model):
    STATUS_IDLE = "idle"
    STATUS_GROWING = "growing"
    STATUS_FALLOW = "fallow"
    STATUS_CHOICES = [
        (STATUS_IDLE, "空闲"),
        (STATUS_GROWING, "在种"),
        (STATUS_FALLOW, "休耕"),
    ]

    greenhouse = models.ForeignKey(
        Greenhouse, on_delete=models.CASCADE, related_name="zones"
    )
    zone_code = models.CharField(max_length=40)
    crop_name = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["greenhouse_id", "zone_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["greenhouse", "zone_code"],
                name="uniq_zone_code_per_greenhouse",
            )
        ]

    def __str__(self):
        return f"{self.greenhouse.name}/{self.zone_code}"


class ClimateLog(models.Model):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="climate_logs")
    recorded_at = models.DateTimeField()
    temp_c = models.DecimalField(max_digits=5, decimal_places=2)
    humidity_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(20), MaxValueValidator(100)],
    )
    par_umol = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    co2_ppm = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Climate@{self.zone_id} {self.recorded_at}"


class IrrigationCycle(models.Model):
    STATUS_SCHEDULED = "scheduled"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "已排程"),
        (STATUS_RUNNING, "进行中"),
        (STATUS_DONE, "已完成"),
        (STATUS_SKIPPED, "已跳过"),
    ]

    zone = models.ForeignKey(
        Zone, on_delete=models.CASCADE, related_name="irrigation_cycles"
    )
    start_at = models.DateTimeField()
    duration_min = models.PositiveIntegerField(default=30)
    water_liters = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_at"]

    def __str__(self):
        return f"Irrig@{self.zone_id} {self.start_at} ({self.status})"


BILLING_MONTH_VALIDATOR = RegexValidator(
    regex=r"^\d{4}-(0[1-9]|1[0-2])$",
    message="账期月格式须为 YYYY-MM，如 2026-09",
)


class WaterShareBill(models.Model):
    """灌溉水费分摊单：按温室 + 账期月归集轮灌水量，封账后固化。"""

    greenhouse = models.ForeignKey(
        Greenhouse, on_delete=models.CASCADE, related_name="water_share_bills"
    )
    billing_month = models.CharField(
        max_length=7, validators=[BILLING_MONTH_VALIDATOR]
    )
    price_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(0)],
    )
    sealed_at = models.DateTimeField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-billing_month", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["greenhouse", "billing_month"],
                name="uniq_bill_per_greenhouse_month",
            )
        ]

    @property
    def is_sealed(self):
        return self.sealed_at is not None

    def total_water_liters(self):
        """已挂轮灌的水量加总（升）。"""
        return self.entries.aggregate(
            s=Coalesce(Sum("cycle__water_liters"), Decimal("0"))
        )["s"]

    def __str__(self):
        return f"Bill@{self.greenhouse_id} {self.billing_month}"


class WaterShareEntry(models.Model):
    """分摊明细：把一笔轮灌挂入一张分摊单。"""

    bill = models.ForeignKey(
        WaterShareBill, on_delete=models.CASCADE, related_name="entries"
    )
    cycle = models.ForeignKey(
        IrrigationCycle, on_delete=models.CASCADE, related_name="share_entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle"],
                name="uniq_cycle_per_bill_entry",
            )
        ]

    def __str__(self):
        return f"Entry bill={self.bill_id} cycle={self.cycle_id}"
