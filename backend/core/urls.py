from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClimateLogViewSet,
    GreenhouseViewSet,
    IrrigationCycleViewSet,
    WaterShareBillViewSet,
    WaterShareEntryViewSet,
    ZoneViewSet,
    dashboard_stats,
)

router = DefaultRouter()
router.register("greenhouses", GreenhouseViewSet, basename="greenhouse")
router.register("zones", ZoneViewSet, basename="zone")
router.register("climate-logs", ClimateLogViewSet, basename="climate-log")
router.register("irrigation-cycles", IrrigationCycleViewSet, basename="irrigation-cycle")
router.register("water-share-bills", WaterShareBillViewSet, basename="water-share-bill")
router.register("water-share-entries", WaterShareEntryViewSet, basename="water-share-entry")

urlpatterns = [
    path("dashboard/", dashboard_stats, name="dashboard"),
    path("", include(router.urls)),
]
