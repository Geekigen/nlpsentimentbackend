# Delivery drivers sentiment analysis backend

Django API for delivery-driver ratings. A customer comment on a delivery is scored with AI with NLP and stored as a 1–5 star rating. The same database is used by the desk and by the MCP server.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`. Do not commit that file.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret. Replace `change-me`. |
| `DJANGO_DEBUG` | `true` for local development. |
| `DJANGO_ALLOWED_HOSTS` | Hosts Django will accept. |
| `OPENAI_API_KEY` | Key used to score comments and answer Ask AI. |
| `OPENAI_MODEL` | Model name. Defaults to `gpt-4o-mini`. |
| `KUTUMA_API_KEY` | Desk key. The frontend exchanges it for a JWT. |
| `JWT_SECRET` | Signs access tokens. |
| `JWT_ACCESS_MINUTES` | Token lifetime. Defaults to 30. |
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API. |
| `CSRF_TRUSTED_ORIGINS` | Origins trusted for Django admin. |
| `MCP_HOST` / `MCP_PORT` | Bind address for `mcp_server.py --http`. Defaults to `127.0.0.1:8001`. |

Create the database, a superuser, and start the API:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

`migrate` loads five drivers and 50 deliveries, each with one already-scored comment. It does not call the model. A newly submitted comment is scored only when analysis runs.

Django admin is at `http://127.0.0.1:8000/admin/`. The superuser can add an admin there. A new user is staff and is not a superuser. That admin can sign in to Ask AI and has 15 chat requests. The superuser is not capped.

## API

Every route except the two login routes requires `Authorization: Bearer <access>`.

- `POST /api/auth/token/` with header `X-Api-Key` returns the desk JWT.
- `POST /api/auth/admin/` with `username` and `password` returns a staff JWT for an active admin.
- `GET /api/drivers/` and `POST /api/drivers/`
- `GET /api/drivers/<id>/` includes an aspect breakdown and `average_stars`
- `GET /api/deliveries/?driver=<id>` and `POST /api/deliveries/`
- `GET /api/comments/?driver=<id>&sentiment=positive`
- `POST /api/comments/` stores a comment without scoring it. Limit: 2 new comments per IP per minute.
- `POST /api/comments/<id>/analyze/` scores the comment and stores 1–5 stars.
- `GET /api/rankings/` returns `top_driver` and the ranked list.
- `POST /api/ask/` answers one question from the live rankings. Requires the staff JWT. Limit: 6 questions per IP per minute, and 15 questions total for an admin who is not a superuser.

A missing or rejected model key returns `API key error` and does not include the key.

## How a comment is scored

`comments.sentiment.analyze_driver_comment` sends the comment to the model named by `OPENAI_MODEL`. The result is:

- sentiment: positive, negative, neutral, or mixed
- a score from −1 to 1, mapped to 1–5 stars
- a one-sentence summary and short highlights
- punctuality, courtesy, package care, communication, and professionalism, or `not_mentioned`

A score of 0.6 or higher is 5 stars, 0.2 is 4, −0.2 is 3, −0.6 is 2, and anything lower is 1.

## MCP

Stdio, for a local agent:

```bash
.venv/bin/python mcp_server.py
```

Streamable HTTP:

```bash
.venv/bin/python mcp_server.py --http
```

The HTTP endpoint is `http://127.0.0.1:8001/mcp`. On the hosted desk, remote agents use `https://realestdemo.online/mcp`.

Every tool asks for the Django admin username and password and runs only for an active admin. Tools: `list_drivers`, `get_driver_performance`, `list_comments`, `analyze_comment`, `record_customer_comment`, `register_driver`.
