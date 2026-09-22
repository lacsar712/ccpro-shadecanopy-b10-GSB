from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClimateLogViewSet,
    GreenhouseViewSet,
    IrrigationCycleViewSet,
    WaterBillViewSet,
    ZoneViewSet,
    dashboard_stats,
    water_fee_reconcile,
)

router = DefaultRouter()
router.register("greenhouses", GreenhouseViewSet, basename="greenhouse")
router.register("zones", ZoneViewSet, basename="zone")
router.register("climate-logs", ClimateLogViewSet, basename="climate-log")
router.register("irrigation-cycles", IrrigationCycleViewSet, basename="irrigation-cycle")
router.register("water-bills", WaterBillViewSet, basename="water-bill")

urlpatterns = [
    path("dashboard/", dashboard_stats, name="dashboard"),
    path("water-fee-reconcile/", water_fee_reconcile, name="water-fee-reconcile"),
    path("", include(router.urls)),
]
