from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Greenhouse, IrrigationCycle, WaterBill, WaterBillItem, Zone

User = get_user_model()


class WaterBillAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester", password="123456", role=User.ROLE_GROWER
        )
        self.client.force_authenticate(self.user)

        self.gh1 = Greenhouse.objects.create(name="一号棚", area_m2=Decimal("100"))
        self.gh2 = Greenhouse.objects.create(name="二号棚", area_m2=Decimal("200"))
        self.zone_a = Zone.objects.create(
            greenhouse=self.gh1, zone_code="A", status=Zone.STATUS_GROWING
        )
        self.zone_b = Zone.objects.create(
            greenhouse=self.gh1, zone_code="B", status=Zone.STATUS_GROWING
        )
        self.zone_c = Zone.objects.create(
            greenhouse=self.gh2, zone_code="C", status=Zone.STATUS_GROWING
        )

        now = timezone.now()
        self.c1 = IrrigationCycle.objects.create(
            zone=self.zone_a, start_at=now, water_liters=Decimal("200.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        self.c2 = IrrigationCycle.objects.create(
            zone=self.zone_b, start_at=now, water_liters=Decimal("150.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        self.c3 = IrrigationCycle.objects.create(
            zone=self.zone_c, start_at=now, water_liters=Decimal("80.00"),
            status=IrrigationCycle.STATUS_DONE,
        )
        self.c_zero = IrrigationCycle.objects.create(
            zone=self.zone_a, start_at=now, water_liters=Decimal("0.00"),
            status=IrrigationCycle.STATUS_DONE,
        )

    def make_bill(self, greenhouse=None, period="2026-09", price="0.0060"):
        return WaterBill.objects.create(
            greenhouse=greenhouse or self.gh1,
            period_month=period,
            price_per_liter=Decimal(price),
        )

    def attach(self, bill, ids, expected=None):
        return self.client.post(
            f"/api/water-bills/{bill.id}/items/",
            {"irrigationCycleIds": ids},
            format="json",
        )

    # ---------- 创建 / 唯一约束 ----------

    def test_create_bill_and_detail_totals(self):
        resp = self.client.post(
            "/api/water-bills/",
            {
                "greenhouseId": self.gh1.id,
                "periodMonth": "2026-09",
                "pricePerLiter": "0.0060",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data["closedAt"])
        bill_id = resp.data["id"]

        # 用 API 挂明细
        resp = self.client.post(
            f"/api/water-bills/{bill_id}/items/",
            {"irrigationCycleIds": [self.c1.id, self.c2.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        resp = self.client.get(f"/api/water-bills/{bill_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["items"]), 2)
        self.assertEqual(Decimal(str(resp.data["totalLiters"])), Decimal("350.00"))
        # 350 × 0.006 = 2.10
        self.assertAlmostEqual(float(resp.data["totalFee"]), 2.10, delta=0.01)

    def test_unique_greenhouse_month(self):
        self.make_bill(period="2026-09")
        resp = self.client.post(
            "/api/water-bills/",
            {
                "greenhouseId": self.gh1.id,
                "periodMonth": "2026-09",
                "pricePerLiter": "0.0050",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # 不同温室同月允许
        resp = self.client.post(
            "/api/water-bills/",
            {
                "greenhouseId": self.gh2.id,
                "periodMonth": "2026-09",
                "pricePerLiter": "0.0050",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_period_month_format(self):
        for bad in ["2026-9", "2026/09", "2026-13", "abcd-09"]:
            resp = self.client.post(
                "/api/water-bills/",
                {
                    "greenhouseId": self.gh1.id,
                    "periodMonth": bad,
                    "pricePerLiter": "0.0050",
                },
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, bad)

    # ---------- 挂明细规则 ----------

    def test_attach_rejects_cycle_of_other_greenhouse(self):
        bill = self.make_bill()
        resp = self.attach(bill, [self.c1.id, self.c3.id])
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(WaterBillItem.objects.filter(bill=bill).count(), 0)

    def test_attach_rejects_already_billed_cycle(self):
        bill1 = self.make_bill(period="2026-08")
        bill2 = self.make_bill(period="2026-07")
        self.assertEqual(self.attach(bill1, [self.c1.id]).status_code, status.HTTP_201_CREATED)
        resp = self.attach(bill2, [self.c1.id])
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        # 同一单内重复提交也拒绝
        resp = self.attach(bill1, [self.c1.id, self.c1.id])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attach_after_close_conflict(self):
        bill = self.make_bill()
        self.attach(bill, [self.c1.id, self.c2.id])
        self.assertEqual(
            self.client.post(f"/api/water-bills/{bill.id}/close/").status_code,
            status.HTTP_200_OK,
        )
        other = IrrigationCycle.objects.create(
            zone=self.zone_a, start_at=timezone.now(), water_liters=Decimal("10.00")
        )
        resp = self.attach(bill, [other.id])
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    # ---------- 封账 ----------

    def test_close_requires_at_least_two_items(self):
        bill = self.make_bill(period="2026-08")
        self.attach(bill, [self.c1.id])
        resp = self.client.post(f"/api/water-bills/{bill.id}/close/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        bill.refresh_from_db()
        self.assertIsNone(bill.closed_at)

    def test_close_requires_positive_total(self):
        bill = self.make_bill(period="2026-08")
        other_zero = IrrigationCycle.objects.create(
            zone=self.zone_b, start_at=timezone.now(), water_liters=Decimal("0.00")
        )
        self.attach(bill, [self.c_zero.id, other_zero.id])
        resp = self.client.post(f"/api/water-bills/{bill.id}/close/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIsNone(WaterBill.objects.get(pk=bill.id).closed_at)

    def test_close_success_and_double_close(self):
        bill = self.make_bill()
        self.attach(bill, [self.c1.id, self.c2.id])
        resp = self.client.post(f"/api/water-bills/{bill.id}/close/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data["closedAt"])
        resp = self.client.post(f"/api/water-bills/{bill.id}/close/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_closed_bill_is_locked(self):
        bill = self.make_bill()
        self.attach(bill, [self.c1.id, self.c2.id])
        self.client.post(f"/api/water-bills/{bill.id}/close/")

        resp = self.client.patch(
            f"/api/water-bills/{bill.id}/",
            {"pricePerLiter": "0.0090"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.delete(f"/api/water-bills/{bill.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        item_id = bill.items.first().id
        resp = self.client.post(f"/api/water-bills/{bill.id}/items/{item_id}/remove/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_remove_item_before_close(self):
        bill = self.make_bill()
        self.attach(bill, [self.c1.id, self.c2.id])
        item_id = bill.items.get(irrigation_cycle=self.c1).id
        resp = self.client.post(f"/api/water-bills/{bill.id}/items/{item_id}/remove/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            WaterBillItem.objects.filter(bill=bill).count(), 1
        )
        # 移除后该轮灌可以挂到别的未封账单
        other = self.make_bill(period="2026-08")
        resp = self.attach(other, [self.c1.id])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # ---------- 费用对账 ----------

    def test_reconcile_totals_per_greenhouse(self):
        # gh1: 350 L × 0.006 = 2.10
        bill1 = self.make_bill(period="2026-09", price="0.0060")
        self.attach(bill1, [self.c1.id, self.c2.id])
        # gh2: 80 L × 0.005 = 0.40
        bill2 = self.make_bill(greenhouse=self.gh2, period="2026-09", price="0.0050")
        self.attach(bill2, [self.c3.id])
        # gh1 第二张：0 升 → 0.00
        bill3 = self.make_bill(period="2026-07", price="0.0060")

        resp = self.client.get("/api/water-fee-reconcile/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = {r["greenhouseId"]: r for r in resp.data["results"]}

        r1 = rows[self.gh1.id]
        self.assertEqual(r1["billCount"], 2)
        self.assertEqual(Decimal(str(r1["totalLiters"])), Decimal("350.00"))
        self.assertAlmostEqual(float(r1["greenhouseTotalFee"]), 2.10, delta=0.01)
        self.assertLessEqual(float(r1["diff"]), 0.01)
        self.assertEqual(
            Decimal(str(r1["greenhouseTotalFee"])),
            Decimal(str(r1["billsTotalFee"])),
        )

        r2 = rows[self.gh2.id]
        self.assertAlmostEqual(float(r2["greenhouseTotalFee"]), 0.40, delta=0.01)
