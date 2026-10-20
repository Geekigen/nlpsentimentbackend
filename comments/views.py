from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from comments.chat import answer_question
from comments.quota import AskLimitReached, asks_remaining, consume_ask
from comments.models import Comment, Delivery
from comments.queries import annotated_drivers, aspect_breakdown, dominant_sentiment, ranked_drivers
from comments.sentiment import SentimentError, SentimentUnavailable
from comments.serializers import (
    CommentSerializer,
    DeliverySerializer,
    DriverSerializer,
    RankingSerializer,
    rounded_stars,
)
from comments.auth import (
    StaffJWTAuthentication,
    api_key_matches,
    issue_access_token,
    issue_staff_token,
)
from comments.services import analyze_saved_comment, submit_comment
from comments.throttles import AskThrottle, CommentCreateThrottle


class DriverViewSet(viewsets.ModelViewSet):
    queryset = annotated_drivers()
    serializer_class = DriverSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return annotated_drivers()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        annotated = self.get_queryset().get(pk=driver.pk)
        return Response(self.get_serializer(annotated).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        driver = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        payload = self.get_serializer(driver).data
        payload["aspects"] = aspect_breakdown(driver)
        return Response(payload)


class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.select_related("driver")
    serializer_class = DeliverySerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        driver_id = self.request.query_params.get("driver")
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        return queryset


class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.select_related("driver", "delivery")
    serializer_class = CommentSerializer
    throttle_classes = [CommentCreateThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def throttled(self, request, wait):
        raise Throttled(detail="Only 2 comments per IP per minute.")

    def get_queryset(self):
        queryset = super().get_queryset()
        driver_id = self.request.query_params.get("driver")
        sentiment = self.request.query_params.get("sentiment")
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        if sentiment:
            queryset = queryset.filter(sentiment=sentiment)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery = serializer.validated_data["delivery"]
        comment = submit_comment(
            delivery=delivery,
            body=serializer.validated_data["body"],
            customer_name=serializer.validated_data.get("customer_name", ""),
        )
        output = self.get_serializer(comment)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="analyze")
    def analyze(self, request, pk=None):
        comment = self.get_object()
        if comment.analysis_status == Comment.AnalysisStatus.ANALYZED and comment.sentiment:
            return Response(self.get_serializer(comment).data)
        try:
            comment = analyze_saved_comment(comment)
        except SentimentUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except SentimentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(self.get_serializer(comment).data)


class TokenView(APIView):
    """Exchange the frontend API key for a short-lived JWT."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if not settings.KUTUMA_API_KEY:
            return Response({"detail": "API key error"}, status=503)
        presented = request.headers.get("X-Api-Key", "")
        if not api_key_matches(presented):
            return Response({"detail": "API key error"}, status=401)
        return Response(
            {
                "access": issue_access_token(),
                "token_type": "Bearer",
                "expires_in": settings.JWT_ACCESS_MINUTES * 60,
            }
        )


class RankingView(APIView):
    def get(self, request):
        rankings = []
        for index, driver in enumerate(ranked_drivers(), start=1):
            rankings.append(
                {
                    "rank": index,
                    "id": driver.pk,
                    "name": driver.name,
                    "employee_code": driver.employee_code,
                    "average_stars": rounded_stars(driver),
                    "comment_count": driver.comment_count,
                    "dominant_sentiment": dominant_sentiment(driver),
                }
            )
        payload = RankingSerializer(rankings, many=True).data
        return Response(
            {
                "top_driver": payload[0] if payload else None,
                "rankings": payload,
            }
        )


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class AskTurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=2000, trim_whitespace=True)


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=1, max_length=500, trim_whitespace=True)
    history = AskTurnSerializer(many=True, required=False, max_length=8)


class AdminLoginView(APIView):
    """Issue a short-lived staff JWT for an active Django admin."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Admin login failed."}, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active or not user.is_staff:
            return Response({"detail": "Admin login failed."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(
            {
                "access": issue_staff_token(user.get_username()),
                "token_type": "Bearer",
                "expires_in": settings.JWT_ACCESS_MINUTES * 60,
                "asks_remaining": asks_remaining(user),
            }
        )


class AskView(APIView):
    """Answer one admin question from the live driver ratings."""

    authentication_classes = [StaffJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AskThrottle]

    def throttled(self, request, wait):
        raise Throttled(detail="Only 6 questions per IP per minute.")

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_user_model().objects.filter(username=request.user.username, is_active=True, is_staff=True).first()
        if user is None:
            return Response({"detail": "Admin login is required."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            remaining = consume_ask(user)
        except AskLimitReached as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        try:
            blocks = answer_question(
                serializer.validated_data["question"],
                serializer.validated_data.get("history", []),
            )
        except SentimentUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except SentimentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"blocks": blocks, "asks_remaining": remaining})
