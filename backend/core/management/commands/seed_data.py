from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    WaterBill,
    WaterBillItem,
    Zone,
)

User = get_user_model()


class Command(BaseCommand):
    help = "初始化演示账号与温室气候/轮灌种子数据"

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@shadecanopy.local",
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("123456")
        admin.role = User.ROLE_ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(self.style.SUCCESS(f"admin {'created' if created else 'updated'}"))

        grower, created = User.objects.get_or_create(
            username="grower",
            defaults={
                "email": "grower@shadecanopy.local",
                "role": User.ROLE_GROWER,
            },
        )
        grower.set_password("123456")
        grower.role = User.ROLE_GROWER
        grower.save()
        self.stdout.write(self.style.SUCCESS(f"grower {'created' if created else 'updated'}"))

        if Greenhouse.objects.exists():
            self.stdout.write("温室数据已存在，跳过业务种子写入。")
            return

        g1 = Greenhouse.objects.create(
            name="东坡一号棚",
            location="东区 A 排",
            area_m2=Decimal("1200.00"),
            notes="番茄与叶菜混作示范棚",
        )
        g2 = Greenhouse.objects.create(
            name="西篱二号棚",
            location="西区 B 排",
            area_m2=Decimal("860.50"),
            notes="草莓高架栽培",
        )

        z1 = Zone.objects.create(
            greenhouse=g1, zone_code="A-01", crop_name="樱桃番茄", status=Zone.STATUS_GROWING
        )
        z2 = Zone.objects.create(
            greenhouse=g1, zone_code="A-02", crop_name="油麦菜", status=Zone.STATUS_GROWING
        )
        z3 = Zone.objects.create(
            greenhouse=g1, zone_code="A-03", crop_name="", status=Zone.STATUS_IDLE
        )
        z4 = Zone.objects.create(
            greenhouse=g2, zone_code="B-01", crop_name="红颜草莓", status=Zone.STATUS_GROWING
        )
        z5 = Zone.objects.create(
            greenhouse=g2, zone_code="B-02", crop_name="章姬草莓", status=Zone.STATUS_FALLOW
        )

        now = timezone.now()
        ClimateLog.objects.bulk_create(
            [
                ClimateLog(
                    zone=z1,
                    recorded_at=now - timedelta(hours=2),
                    temp_c=Decimal("24.50"),
                    humidity_pct=Decimal("68.00"),
                    par_umol=Decimal("420.00"),
                    co2_ppm=Decimal("650.00"),
                ),
                ClimateLog(
                    zone=z1,
                    recorded_at=now - timedelta(hours=6),
                    temp_c=Decimal("22.10"),
                    humidity_pct=Decimal("72.50"),
                    par_umol=Decimal("180.00"),
                    co2_ppm=Decimal("700.00"),
                ),
                ClimateLog(
                    zone=z2,
                    recorded_at=now - timedelta(hours=3),
                    temp_c=Decimal("23.80"),
                    humidity_pct=Decimal("70.00"),
                    par_umol=Decimal("390.00"),
                    co2_ppm=Decimal("620.00"),
                ),
                ClimateLog(
                    zone=z4,
                    recorded_at=now - timedelta(hours=1),
                    temp_c=Decimal("21.20"),
                    humidity_pct=Decimal("75.00"),
                    par_umol=Decimal("350.00"),
                    co2_ppm=Decimal("580.00"),
                ),
                ClimateLog(
                    zone=z4,
                    recorded_at=now - timedelta(hours=20),
                    temp_c=Decimal("18.60"),
                    humidity_pct=Decimal("80.00"),
                    par_umol=Decimal("50.00"),
                    co2_ppm=Decimal("720.00"),
                ),
            ]
        )

        today = now.replace(hour=9, minute=0, second=0, microsecond=0)
        IrrigationCycle.objects.bulk_create(
            [
                IrrigationCycle(
                    zone=z1,
                    start_at=today + timedelta(hours=1),
                    duration_min=25,
                    water_liters=Decimal("180.00"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
                IrrigationCycle(
                    zone=z2,
                    start_at=today + timedelta(hours=2),
                    duration_min=20,
                    water_liters=Decimal("120.00"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
                IrrigationCycle(
                    zone=z4,
                    start_at=today - timedelta(hours=3),
                    duration_min=30,
                    water_liters=Decimal("95.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(
                    zone=z1,
                    start_at=today - timedelta(days=1, hours=2),
                    duration_min=25,
                    water_liters=Decimal("175.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(
                    zone=z5,
                    start_at=today + timedelta(hours=4),
                    duration_min=15,
                    water_liters=Decimal("40.00"),
                    status=IrrigationCycle.STATUS_SKIPPED,
                ),
            ]
        )

        # ---- 水费分摊演示数据（当前月/上月，含已封、可封、不可封） ----
        current_anchor = now.replace(
            day=min(15, now.day), hour=9, minute=0, second=0, microsecond=0
        )
        if current_anchor > now:
            current_anchor -= timedelta(days=1)
        prev_month_anchor = (
            (current_anchor.replace(day=1) - timedelta(days=1))
            .replace(day=15, hour=9, minute=0, second=0, microsecond=0)
        )
        current_period = current_anchor.strftime("%Y-%m")
        prev_period = prev_month_anchor.strftime("%Y-%m")

        # g1 上月两笔（已封账单）
        prev_c1 = IrrigationCycle.objects.create(
            zone=z1,
            start_at=prev_month_anchor,
            duration_min=25,
            water_liters=Decimal("220.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        prev_c2 = IrrigationCycle.objects.create(
            zone=z2,
            start_at=prev_month_anchor + timedelta(hours=2),
            duration_min=20,
            water_liters=Decimal("130.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        # g1 当月两笔（可封账单）
        curr_c1 = IrrigationCycle.objects.create(
            zone=z1,
            start_at=current_anchor,
            duration_min=25,
            water_liters=Decimal("200.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        curr_c2 = IrrigationCycle.objects.create(
            zone=z2,
            start_at=current_anchor + timedelta(hours=2),
            duration_min=20,
            water_liters=Decimal("150.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        # g2 当月两笔但总水量为 0（不可封：总水量非正）
        zero_c1 = IrrigationCycle.objects.create(
            zone=z4,
            start_at=current_anchor + timedelta(hours=1),
            duration_min=30,
            water_liters=Decimal("0.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        zero_c2 = IrrigationCycle.objects.create(
            zone=z5,
            start_at=current_anchor + timedelta(hours=3),
            duration_min=15,
            water_liters=Decimal("0.00"),
            status=IrrigationCycle.STATUS_SKIPPED,
        )
        # g2 上月仅一笔（不可封：不足两笔）
        single_c1 = IrrigationCycle.objects.create(
            zone=z4,
            start_at=prev_month_anchor + timedelta(hours=1),
            duration_min=30,
            water_liters=Decimal("50.00"),
            status=IrrigationCycle.STATUS_DONE,
        )

        closed_bill = WaterBill.objects.create(
            greenhouse=g1,
            period_month=prev_period,
            price_per_liter=Decimal("0.0050"),
            closed_at=timezone.now(),
        )
        WaterBillItem.objects.bulk_create(
            [
                WaterBillItem(bill=closed_bill, irrigation_cycle=prev_c1),
                WaterBillItem(bill=closed_bill, irrigation_cycle=prev_c2),
            ]
        )

        ready_bill = WaterBill.objects.create(
            greenhouse=g1,
            period_month=current_period,
            price_per_liter=Decimal("0.0060"),
        )
        WaterBillItem.objects.bulk_create(
            [
                WaterBillItem(bill=ready_bill, irrigation_cycle=curr_c1),
                WaterBillItem(bill=ready_bill, irrigation_cycle=curr_c2),
            ]
        )

        zero_bill = WaterBill.objects.create(
            greenhouse=g2,
            period_month=current_period,
            price_per_liter=Decimal("0.0060"),
        )
        WaterBillItem.objects.bulk_create(
            [
                WaterBillItem(bill=zero_bill, irrigation_cycle=zero_c1),
                WaterBillItem(bill=zero_bill, irrigation_cycle=zero_c2),
            ]
        )

        short_bill = WaterBill.objects.create(
            greenhouse=g2,
            period_month=prev_period,
            price_per_liter=Decimal("0.0050"),
        )
        WaterBillItem.objects.create(bill=short_bill, irrigation_cycle=single_c1)

        self.stdout.write(
            self.style.SUCCESS(
                f"种子完成：温室 {Greenhouse.objects.count()}，分区 {Zone.objects.count()}，"
                f"气候 {ClimateLog.objects.count()}，轮灌 {IrrigationCycle.objects.count()}，"
                f"水费分摊单 {WaterBill.objects.count()}（含已封/可封/不可封）"
            )
        )
