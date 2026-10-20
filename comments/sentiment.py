from typing import Literal

from django.conf import settings
from openai import APIError, OpenAI
from pydantic import BaseModel, Field


Rating = Literal["positive", "negative", "neutral", "not_mentioned"]
Overall = Literal["positive", "negative", "neutral", "mixed"]


class SentimentError(Exception):
    """The comment could not be scored."""


class SentimentUnavailable(SentimentError):
    """Scoring is not configured or the provider could not be reached."""


class AspectScore(BaseModel):
    rating: Rating
    note: str = ""


class DriverAspects(BaseModel):
    punctuality: AspectScore
    courtesy: AspectScore
    package_care: AspectScore
    communication: AspectScore
    professionalism: AspectScore


class DriverSentiment(BaseModel):
    sentiment: Overall
    score: float = Field(ge=-1, le=1)
    summary: str
    aspects: DriverAspects
    highlights: list[str]


INSTRUCTIONS = """
You score customer comments about a delivery driver's performance.
Judge only the driver: punctuality, courtesy, care of the package, communication, and professionalism.
Ignore price, the product, and the company unless the comment clearly describes what the driver did.
sentiment is the overall judgment of the driver.
score runs from -1 (very poor) to 1 (excellent). Use 0 when the comment does not describe the driver.
For each aspect, use not_mentioned when the comment does not speak to it.
summary is one sentence a dispatcher can act on.
highlights are short phrases taken from the comment.
""".strip()


def _provider_message(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    message = str(exc).lower()
    if status in (401, 403) or "invalid_api_key" in message or "api key" in message or "incorrect api key" in message:
        return "API key error"
    return "OpenAI request failed."


def analyze_driver_comment(comment: str) -> DriverSentiment:
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        raise SentimentUnavailable("API key error")

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.parse(
            model=settings.OPENAI_MODEL,
            instructions=INSTRUCTIONS,
            input=comment,
            text_format=DriverSentiment,
        )
    except APIError as exc:
        raise SentimentUnavailable(_provider_message(exc)) from exc

    parsed = response.output_parsed
    if parsed is None:
        raise SentimentError("OpenAI returned no sentiment.")
    return parsed
