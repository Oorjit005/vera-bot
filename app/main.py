import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import config
from app.store import store

app = FastAPI()
_START_TIME = time.time()

VALID_SCOPES = ("category", "merchant", "customer", "trigger")
DEFAULT_NOW = "2026-04-26T10:00:00Z"


def now_iso_ms() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


@app.post("/v1/context")
async def post_context(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={
                "accepted": False, "reason": "invalid_payload", "details": "body is not valid JSON",
            })
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={
                "accepted": False, "reason": "invalid_payload", "details": "body must be a JSON object",
            })

        scope = body.get("scope")
        if scope not in VALID_SCOPES:
            return JSONResponse(status_code=400, content={
                "accepted": False, "reason": "invalid_scope", "details": f"scope must be one of {VALID_SCOPES}",
            })

        context_id = body.get("context_id")
        version = body.get("version")
        payload = body.get("payload")
        if (
            not isinstance(context_id, str) or not context_id
            or isinstance(version, bool) or not isinstance(version, int)
            or not isinstance(payload, dict)
        ):
            return JSONResponse(status_code=400, content={
                "accepted": False, "reason": "invalid_payload",
                "details": "context_id must be a non-empty string, version an int, payload an object",
            })

        stored_at = now_iso_ms()
        result, current_version = store.put(scope, context_id, version, payload, stored_at)
        if result == "stale":
            return JSONResponse(status_code=409, content={
                "accepted": False, "reason": "stale_version", "current_version": current_version,
            })

        try:
            from app.compose import precompose
            precompose.schedule_for(scope, context_id)
        except Exception:
            pass

        return JSONResponse(status_code=200, content={
            "accepted": True, "ack_id": f"ack_{context_id}_v{version}", "stored_at": stored_at,
        })
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "accepted": False, "reason": "invalid_payload", "details": str(e),
        })


@app.post("/v1/tick")
async def post_tick(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        now = body.get("now") if isinstance(body, dict) else None
        if not now:
            now = store.last_now or DEFAULT_NOW
        store.last_now = now

        try:
            from app.tick import select_and_compose
            available_triggers = body.get("available_triggers") or [] if isinstance(body, dict) else []
            actions = await select_and_compose(now, available_triggers)
            return JSONResponse(status_code=200, content={"actions": actions})
        except ImportError:
            return JSONResponse(status_code=200, content={"actions": []})
    except Exception:
        return JSONResponse(status_code=200, content={"actions": []})


@app.post("/v1/reply")
async def post_reply(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            from app.reply.respond import respond
            result = await respond(body if isinstance(body, dict) else {})
            return JSONResponse(status_code=200, content=result)
        except ImportError:
            return JSONResponse(status_code=200, content={
                "action": "wait", "wait_seconds": 60,
                "rationale": "stub: reply handling not implemented yet (S5)",
            })
    except Exception:
        return JSONResponse(status_code=200, content={
            "action": "wait", "wait_seconds": 300, "rationale": "internal recovery",
        })


@app.get("/v1/healthz")
async def get_healthz():
    try:
        return JSONResponse(status_code=200, content={
            "status": "ok",
            "uptime_seconds": int(time.time() - _START_TIME),
            "contexts_loaded": store.counts(),
        })
    except Exception:
        return JSONResponse(status_code=200, content={
            "status": "ok", "uptime_seconds": 0,
            "contexts_loaded": {"category": 0, "merchant": 0, "customer": 0, "trigger": 0},
        })


@app.get("/v1/metadata")
async def get_metadata():
    return JSONResponse(status_code=200, content={
        "team_name": config.TEAM_NAME,
        "team_members": config.TEAM_MEMBERS,
        "model": f"{config.WRITER_MODEL} (writer) + deterministic brief/validator/templates",
        "approach": config.APPROACH,
        "contact_email": config.CONTACT_EMAIL,
        "version": config.BOT_VERSION,
        "submitted_at": config.SUBMITTED_AT,
    })


@app.post("/v1/teardown")
async def post_teardown():
    try:
        from app.writer import reset_writer_state
        reset_writer_state()
    except Exception:
        pass
    store.clear()
    return JSONResponse(status_code=200, content={"ok": True})
