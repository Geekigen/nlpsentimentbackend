from rest_framework import serializers

from comments.models import Comment, Delivery, Driver
from comments.queries import dominant_sentiment


def rounded_stars(driver):
    value = getattr(driver, "average_stars", None)
    if value is None:
        return None
    return round(float(value), 1)


class CommentSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.name", read_only=True)
    delivery_reference = serializers.CharField(source="delivery.reference", read_only=True)
    body = serializers.CharField(min_length=8, max_length=250)

    class Meta:
        model = Comment
        fields = [
            "id",
            "driver",
            "driver_name",
            "delivery",
            "delivery_reference",
            "customer_name",
            "order_reference",
            "body",
            "analysis_status",
            "sentiment",
            "score",
            "stars",
            "summary",
            "aspects",
            "highlights",
            "model_name",
            "created_at",
        ]
        read_only_fields = [
            "driver",
            "analysis_status",
            "sentiment",
            "score",
            "stars",
            "summary",
            "aspects",
            "highlights",
            "model_name",
            "created_at",
            "driver_name",
            "delivery_reference",
            "order_reference",
        ]


class DeliverySerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.name", read_only=True)

    class Meta:
        model = Delivery
        fields = ["id", "driver", "driver_name", "reference", "created_at"]
        read_only_fields = ["created_at", "driver_name"]


class DriverSerializer(serializers.ModelSerializer):
    comment_count = serializers.IntegerField(read_only=True)
    average_score = serializers.FloatField(read_only=True)
    average_stars = serializers.SerializerMethodField()
    dominant_sentiment = serializers.SerializerMethodField()
    sentiment_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "name",
            "employee_code",
            "active",
            "comment_count",
            "average_score",
            "average_stars",
            "dominant_sentiment",
            "sentiment_breakdown",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_average_stars(self, driver):
        return rounded_stars(driver)

    def get_dominant_sentiment(self, driver):
        if not hasattr(driver, "positive_count"):
            return None
        return dominant_sentiment(driver)

    def get_sentiment_breakdown(self, driver):
        if not hasattr(driver, "positive_count"):
            return {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
        return {
            "positive": driver.positive_count,
            "negative": driver.negative_count,
            "neutral": driver.neutral_count,
            "mixed": driver.mixed_count,
        }


class RankingSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    id = serializers.IntegerField()
    name = serializers.CharField()
    employee_code = serializers.CharField()
    average_stars = serializers.FloatField()
    comment_count = serializers.IntegerField()
    dominant_sentiment = serializers.CharField(allow_null=True)
