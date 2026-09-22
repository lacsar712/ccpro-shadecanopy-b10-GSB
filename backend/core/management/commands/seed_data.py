from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    WaterShareBill,
    WaterShareEntry,
    Zone,
)

User = get_user_model()


class Command(BaseCommand):
    help = "初始化演示账号与温室气候/轮灌/水费分摊种子数据"

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

        # ---- 灌溉水费分摊种子：可封 / 不可封 / 已封 三种形态 ----
        month_cur = now.strftime("%Y-%m")
        prev_anchor = now.replace(day=1) - timedelta(days=1)
        month_prev = prev_anchor.strftime("%Y-%m")

        def mk_cycle(zone, when, liters):
            return IrrigationCycle.objects.create(
                zone=zone,
                start_at=when,
                duration_min=25,
                water_liters=Decimal(liters),
                status=IrrigationCycle.STATUS_DONE,
            )

        def at(anchor, day, hour):
            return anchor.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)

        # 可封：两笔轮灌、水量加总为正（东坡一号棚 · 当月）
        bill_open_ok = WaterShareBill.objects.create(
            greenhouse=g1,
            billing_month=month_cur,
            price_per_liter=Decimal("0.0032"),
        )
        WaterShareEntry.objects.create(
            bill=bill_open_ok, cycle=mk_cycle(z1, at(now, 8, 8), "160.00")
        )
        WaterShareEntry.objects.create(
            bill=bill_open_ok, cycle=mk_cycle(z2, at(now, 12, 9), "140.00")
        )

        # 已封：上月账单已封账，演示封后禁止再挂（东坡一号棚 · 上月）
        bill_sealed = WaterShareBill.objects.create(
            greenhouse=g1,
            billing_month=month_prev,
            price_per_liter=Decimal("0.0030"),
            sealed_at=now - timedelta(days=3),
        )
        WaterShareEntry.objects.create(
            bill=bill_sealed, cycle=mk_cycle(z1, at(prev_anchor, 10, 8), "170.00")
        )
        WaterShareEntry.objects.create(
            bill=bill_sealed, cycle=mk_cycle(z2, at(prev_anchor, 18, 9), "130.00")
        )

        # 不可封：仅一笔轮灌，不足两笔（西篱二号棚 · 当月）
        bill_short = WaterShareBill.objects.create(
            greenhouse=g2,
            billing_month=month_cur,
            price_per_liter=Decimal("0.0035"),
        )
        WaterShareEntry.objects.create(
            bill=bill_short, cycle=mk_cycle(z4, at(now, 9, 7), "90.00")
        )

        # 不可封：两笔轮灌但水量加总不为正（西篱二号棚 · 上月）
        bill_zero = WaterShareBill.objects.create(
            greenhouse=g2,
            billing_month=month_prev,
            price_per_liter=Decimal("0.0033"),
        )
        WaterShareEntry.objects.create(
            bill=bill_zero, cycle=mk_cycle(z4, at(prev_anchor, 11, 8), "0.00")
        )
        WaterShareEntry.objects.create(
            bill=bill_zero, cycle=mk_cycle(z5, at(prev_anchor, 19, 8), "0.00")
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"种子完成：温室 {Greenhouse.objects.count()}，分区 {Zone.objects.count()}，"
                f"气候 {ClimateLog.objects.count()}，轮灌 {IrrigationCycle.objects.count()}，"
                f"分摊单 {WaterShareBill.objects.count()}，分摊明细 {WaterShareEntry.objects.count()}"
            )
        )
