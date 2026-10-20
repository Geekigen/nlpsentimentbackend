from django.urls import path
from rest_framework.routers import DefaultRouter

from comments.views import (
    AdminLoginView,
    AskView,
    CommentViewSet,
    DeliveryViewSet,
    DriverViewSet,
    RankingView,
    TokenView,
)

router = DefaultRouter()
router.register("drivers", DriverViewSet, basename="driver")
router.register("deliveries", DeliveryViewSet, basename="delivery")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = [
    path("auth/token/", TokenView.as_view(), name="auth-token"),
    path("auth/admin/", AdminLoginView.as_view(), name="auth-admin"),
    path("ask/", AskView.as_view(), name="ask"),
    path("rankings/", RankingView.as_view(), name="rankings"),
    *router.urls,
]
