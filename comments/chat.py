import math
import re

from django.conf import settings
from openai import APIError, OpenAI
from pydantic import BaseModel, Field, ValidationError

from comments.queries import annotated_drivers, aspect_breakdown, dominant_sentiment, ranked_drivers
from comments.sentiment import SentimentError, SentimentUnavailable, _provider_message
from comments.serializers import rounded_stars

_HTML_TAG = re.compile(r"<[^>]*>")


class ChartSpec(BaseModel):
    title: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


class ChatBlock(BaseModel):
    kind: str = "text"
    text: str = ""
    markdown: str = ""
    chart: ChartSpec | None = None


class ChatReply(BaseModel):
    blocks: list[ChatBlock] = Field(default_factory=list, max_length=6)


INSTRUCTIONS = """
You answer questions about delivery-driver ratings for an admin.
Use only the ratings snapshot in the conversation. Do not invent drivers, counts, or scores.
Reply with one or more blocks:
- kind text: a short plain answer in text.
- kind markdown: a simple report in markdown. Headings, paragraphs, lists, and bold only. No HTML and no tables.
- kind chart: one bar chart. labels are driver names or short categories from the snapshot. values are numbers from the snapshot, such as average stars or comment counts. title names the chart.
When the question asks for a report, include a markdown block.
When the question asks for a chart, include a chart block.
Keep the answer about drivers, comments, sentiment, and stars.
Call the scorer "AI with NLP". Do not name the model provider.
""".strip()


def ratings_snapshot() -> dict:
    drivers = []
    for index, driver in enumerate(ranked_drivers(), start=1):
        drivers.append(
            {
                "rank": index,
                "name": driver.name,
                "employee_code": driver.employee_code,
                "average_stars": rounded_stars(driver),
                "comment_count": driver.comment_count,
                "dominant_sentiment": dominant_sentiment(driver),
                "aspects": aspect_breakdown(driver),
            }
        )
    unscored = annotated_drivers().filter(comment_count=0).count()
    return {"ranked_drivers": drivers, "unscored_driver_count": unscored}


def strip_html(value: str) -> str:
    return _HTML_TAG.sub("", value)


def clean_blocks(reply: ChatReply) -> list[dict]:
    cleaned = []
    for block in reply.blocks[:6]:
        kind = _block_kind(block)
        if kind == "text":
            text = strip_html(block.text).strip()
            if text:
                cleaned.append({"kind": "text", "text": text[:4000]})
        elif kind == "markdown":
            markdown = strip_html(block.markdown or block.text).strip()
            if markdown:
                cleaned.append({"kind": "markdown", "markdown": markdown[:8000]})
        elif kind == "chart" and block.chart is not None:
            chart = _clean_chart(block.chart)
            if chart:
                cleaned.append({"kind": "chart", "chart": chart})
    if not cleaned:
        raise SentimentError("AI returned no answer.")
    return cleaned


def _block_kind(block: ChatBlock) -> str:
    kind = block.kind.strip().lower()
    if kind in {"text", "markdown", "chart"}:
        return kind
    if block.chart is not None and block.chart.labels:
        return "chart"
    if block.markdown.strip():
        return "markdown"
    return "text"


def _clean_chart(chart: ChartSpec) -> dict | None:
    labels = []
    values = []
    for label, value in zip(chart.labels, chart.values):
        name = strip_html(label).strip()[:40]
        number = float(value)
        if not name or not math.isfinite(number):
            continue
        labels.append(name)
        values.append(round(number, 2))
        if len(labels) == 12:
            break
    if not labels:
        return None
    title = strip_html(chart.title).strip()[:80] or "Driver ratings"
    return {"title": title, "labels": labels, "values": values}


def answer_question(question: str, history: list[dict]) -> list[dict]:
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        raise SentimentUnavailable("API key error")

    transcript = [f"Ratings snapshot:\n{ratings_snapshot()}"]
    for turn in history:
        transcript.append(f"{turn['role']}: {turn['content']}")
    transcript.append(f"user: {question}")

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.parse(
            model=settings.OPENAI_MODEL,
            instructions=INSTRUCTIONS,
            input="\n\n".join(transcript),
            text_format=ChatReply,
        )
    except APIError as exc:
        raise SentimentUnavailable(_provider_message(exc)) from exc
    except ValidationError as exc:
        raise SentimentError("AI returned no answer.") from exc

    if response.output_parsed is None:
        raise SentimentError("AI returned no answer.")
    return clean_blocks(response.output_parsed)
