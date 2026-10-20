"""MCP server other agents use to query driver-comment sentiment.

Stdio (Cursor and local agents):

    python mcp_server.py

Streamable HTTP on port 8001:

    python mcp_server.py --http
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import authenticate
from django.db import close_old_connections
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from comments.models import Comment, Delivery, Driver
from comments.queries import annotated_drivers, aspect_breakdown, resolve_driver
from comments.sentiment import SentimentError
from comments.serializers import CommentSerializer, DriverSerializer
from comments.services import record_comment

server = MCPServer(
    name="kutuma",
    instructions=(
        "Query Kutuma delivery-driver ratings. Every tool asks for the Django "
        "admin username and password before it runs. A customer comment belongs "
        "to a delivery, and that delivery belongs to a driver. OpenAI scores the "
        "comment from -1 to 1, which is stored as 1 to 5 stars. Identify a "
        "driver by id, employee code, or name."
    ),
)


@contextmanager
def database():
    close_old_connections()
    try:
        yield
    finally:
        close_old_connections()


class AdminLogin(BaseModel):
    username: str
    password: str


def admin_login_ok(username: str, password: str) -> bool:
    """True when the username and password belong to an active Django admin."""
    user = authenticate(username=username.strip(), password=password)
    return bool(user and user.is_active and user.is_staff)


async def require_admin(ctx: Context) -> None:
    result = await ctx.elicit("Enter the Django admin username and password.", AdminLogin)
    if result.action != "accept":
        raise ToolError("Admin login is required.")
    if not admin_login_ok(result.data.username, result.data.password):
        raise ToolError("Admin login failed.")


def _resolve(token: str) -> Driver:
    try:
        return resolve_driver(token)
    except (Driver.DoesNotExist, Driver.MultipleObjectsReturned) as exc:
        raise ToolError(str(exc)) from exc


@server.tool()
async def list_drivers(active_only: bool = False, ctx: Context = None) -> list[dict]:
    """List delivery drivers with average star rating and comment counts."""
    await require_admin(ctx)
    with database():
        queryset = annotated_drivers()
        if active_only:
            queryset = queryset.filter(active=True)
        return list(DriverSerializer(queryset, many=True).data)


@server.tool()
async def get_driver_performance(driver: str, ctx: Context = None) -> dict:
    """Return one driver's score, sentiment mix, aspect breakdown, and recent comments.

    driver: numeric id, employee code such as DRV-014, or a unique part of the name.
    """
    await require_admin(ctx)
    with database():
        match = _resolve(driver)
        annotated = annotated_drivers().get(pk=match.pk)
        comments = match.comments.select_related("driver", "delivery")[:20]
        return {
            "driver": DriverSerializer(annotated).data,
            "aspects": aspect_breakdown(match),
            "comments": CommentSerializer(comments, many=True).data,
        }


@server.tool()
async def list_comments(driver: str = "", sentiment: str = "", limit: int = 20, ctx: Context = None) -> list[dict]:
    """List scored customer comments, optionally filtered by driver and sentiment.

    sentiment: positive, negative, neutral, or mixed.
    """
    await require_admin(ctx)
    with database():
        queryset = Comment.objects.select_related("driver", "delivery")
        if driver:
            queryset = queryset.filter(driver=_resolve(driver))
        if sentiment:
            queryset = queryset.filter(sentiment=sentiment)
        safe_limit = min(max(limit, 1), 100)
        return list(CommentSerializer(queryset[:safe_limit], many=True).data)


@server.tool()
async def analyze_comment(comment: str, ctx: Context = None) -> dict:
    """Score a customer comment with OpenAI. Does not save it."""
    from comments.sentiment import analyze_driver_comment

    await require_admin(ctx)
    try:
        analysis = analyze_driver_comment(comment)
    except SentimentError as exc:
        raise ToolError(str(exc)) from exc
    return analysis.model_dump()


@server.tool()
async def record_customer_comment(
    driver: str,
    comment: str,
    delivery_reference: str,
    customer_name: str = "",
    ctx: Context = None,
) -> dict:
    """Score a comment with OpenAI and store it on a delivery for that driver.

    delivery_reference: an existing delivery code, or a new one to create.
    The delivery's driver must match the driver argument.
    """
    await require_admin(ctx)
    with database():
        match = _resolve(driver)
        reference = delivery_reference.strip()
        if not reference:
            raise ToolError("A delivery reference is required.")
        delivery = Delivery.objects.filter(reference__iexact=reference).first()
        if delivery is None:
            delivery = Delivery.objects.create(driver=match, reference=reference)
        elif delivery.driver_id != match.pk:
            raise ToolError(f"{reference} belongs to another driver.")
        try:
            saved = record_comment(
                delivery=delivery,
                body=comment,
                customer_name=customer_name,
            )
        except SentimentError as exc:
            raise ToolError(str(exc)) from exc
        return CommentSerializer(saved).data


@server.tool()
async def register_driver(name: str, employee_code: str, ctx: Context = None) -> dict:
    """Add a delivery driver that later comments can be scored against."""
    await require_admin(ctx)
    with database():
        code = employee_code.strip().upper()
        if Driver.objects.filter(employee_code__iexact=code).exists():
            raise ToolError(f"Employee code {code} already exists.")
        created = Driver.objects.create(name=name.strip(), employee_code=code)
        annotated = annotated_drivers().get(pk=created.pk)
        return DriverSerializer(annotated).data


def main() -> None:
    if "--http" in sys.argv:
        server.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8001")),
        )
        return
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
