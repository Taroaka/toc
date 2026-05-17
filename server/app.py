from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .image_gen_app import DIST_DIR, router as image_gen_router, shutdown_codex_client
from .line_app import router as line_router


app = FastAPI(title="ToC Local Server")

if DIST_DIR.exists():
    app.mount("/image_gen/assets", StaticFiles(directory=DIST_DIR / "assets"), name="image_gen_assets")


@app.middleware("http")
async def protect_image_gen_routes(request: Request, call_next):  # type: ignore[no-untyped-def]
    return await call_next(request)


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
