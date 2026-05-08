from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .image_gen_app import DIST_DIR, router as image_gen_router, shutdown_codex_client
from .line_app import router as line_router


app = FastAPI(title="ToC Local Server")

if DIST_DIR.exists():
    app.mount("/image_gen/assets", StaticFiles(directory=DIST_DIR / "assets"), name="image_gen_assets")


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.headers.get("x-toc-local-token")
        or request.cookies.get("toc_server_token")
        or request.query_params.get("token")
    )


@app.middleware("http")
async def protect_image_gen_routes(request: Request, call_next):  # type: ignore[no-untyped-def]
    expected = os.environ.get("TOC_SERVER_TOKEN", "").strip()
    auth_disabled = os.environ.get("TOC_SERVER_AUTH_DISABLED", "").strip().lower() in {"1", "true", "yes"}
    path = request.url.path
    protected = path == "/image_gen" or path.startswith("/image_gen/") or path.startswith("/api/")
    if protected and not auth_disabled:
        if not expected:
            return JSONResponse(status_code=401, content={"detail": "TOC_SERVER_TOKEN is required"})
        if _token_from_request(request) != expected:
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    response = await call_next(request)
    if expected and request.query_params.get("token") == expected and path == "/image_gen":
        response.set_cookie("toc_server_token", expected, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return response


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
async def not_found_handler(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.on_event("shutdown")
async def _shutdown() -> None:
    await shutdown_codex_client()


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "running", "line": "/line/webhook", "imageGen": "/image_gen"}


app.include_router(line_router)
app.include_router(image_gen_router)
