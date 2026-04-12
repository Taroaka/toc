#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import time
import urllib.request

import websockets


READER_STATE_JS = r"""
(() => {
  const text = (document.body && document.body.innerText) || "";
  const match = text.match(/(?:Page|Location)\s+(\d+)\s+of\s+(\d+)/);
  const blobImage = Array.from(document.images).find((img) => img.src.startsWith("blob:"));
  const nextButton = document.querySelector('button[aria-label="Next page"]');
  return {
    href: location.href,
    title: document.title,
    textPreview: text.slice(0, 400),
    currentPage: match ? Number(match[1]) : null,
    totalPages: match ? Number(match[2]) : null,
    hasBlobImage: Boolean(blobImage),
    imageCount: document.images.length,
    isLibrary: location.href.includes("kindle-library"),
    isSignIn: /signin/i.test(location.href),
    isReader: Boolean(match && blobImage),
    nextButtonDisabled: nextButton ? Boolean(nextButton.disabled || nextButton.getAttribute("aria-disabled") === "true") : null
  };
})()
"""

NEXT_BUTTON_JS = r"""
(() => {
  const button = document.querySelector('button[aria-label="Next page"]');
  if (!button) {
    return null;
  }
  const rect = button.getBoundingClientRect();
  return {
    x: rect.x + rect.width / 2,
    y: rect.y + rect.height / 2,
    width: rect.width,
    height: rect.height,
    disabled: Boolean(button.disabled || button.getAttribute("aria-disabled") === "true")
  };
})()
"""

VIEWPORT_JS = r"""
(() => ({
  width: window.innerWidth || document.documentElement.clientWidth || 0,
  height: window.innerHeight || document.documentElement.clientHeight || 0
}))()
"""

EXPORT_BLOB_IMAGE_JS = r"""
(() => {
  const image = Array.from(document.images).find((img) => img.src.startsWith("blob:"));
  if (!image) {
    return { error: "blob image not found" };
  }
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);
  return {
    width: image.naturalWidth,
    height: image.naturalHeight,
    data: canvas.toDataURL("image/png").split(",")[1]
  };
})()
"""


def http_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.load(response)


def list_targets(port: int) -> list[dict]:
    data = http_json(f"http://127.0.0.1:{port}/json/list")
    if not isinstance(data, list):
        raise RuntimeError("Unexpected Chrome DevTools response.")
    return [item for item in data if isinstance(item, dict)]


class CdpPage:
    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self.websocket = None
        self.message_id = 0

    async def __aenter__(self) -> "CdpPage":
        self.websocket = await websockets.connect(self.websocket_url, max_size=None)
        await self.call("Runtime.enable")
        await self.call("Page.enable")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.websocket is not None:
            await self.websocket.close()

    async def call(self, method: str, params: dict | None = None) -> dict:
        if self.websocket is None:
            raise RuntimeError("CDP page is not connected.")
        self.message_id += 1
        payload = {"id": self.message_id, "method": method, "params": params or {}}
        await self.websocket.send(json.dumps(payload))
        while True:
            message = json.loads(await self.websocket.recv())
            if message.get("id") != self.message_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP error for {method}: {message['error']}")
            return message.get("result", {})

    async def evaluate(self, expression: str, *, await_promise: bool = False) -> object:
        result = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        return result.get("result", {}).get("value")


class PageAlreadyChangedError(RuntimeError):
    """Raised when the reader page appears to have advanced before a turn click."""


def geometry_is_clickable(geometry: dict | None) -> bool:
    return bool(
        isinstance(geometry, dict)
        and not geometry.get("disabled")
        and isinstance(geometry.get("width"), (int, float))
        and isinstance(geometry.get("height"), (int, float))
        and geometry["width"] > 1
        and geometry["height"] > 1
        and isinstance(geometry.get("x"), (int, float))
        and isinstance(geometry.get("y"), (int, float))
    )


def page_advance_direction(previous_page: int | None, current_page: int | None) -> str:
    if previous_page is None or current_page is None:
        return "unknown"
    if current_page > previous_page:
        return "forward"
    if current_page < previous_page:
        return "backward"
    return "unchanged"


def numbering_mode_changed(
    previous_page: int | None,
    initial_total_pages: int | None,
    current_page: int | None,
    current_total_pages: int | None,
) -> bool:
    return bool(
        previous_page is not None
        and initial_total_pages is not None
        and current_page == previous_page
        and isinstance(current_total_pages, int)
        and current_total_pages != initial_total_pages
    )


def hover_probe_points(viewport_width: int | float, viewport_height: int | float) -> list[dict]:
    width = max(int(viewport_width), 0)
    height = max(int(viewport_height), 0)
    y = max(height // 2, 80)
    right_x = max(width - 60, 60)
    return [
        {"label": "left", "x": 60, "y": y},
        {"label": "right", "x": right_x, "y": y},
    ]


async def read_state(page: CdpPage) -> dict:
    state = await page.evaluate(READER_STATE_JS)
    if not isinstance(state, dict):
        raise RuntimeError("Failed to inspect Kindle page state.")
    return state


def candidate_targets(port: int) -> list[dict]:
    targets = []
    for item in list_targets(port):
        if item.get("type") != "page":
            continue
        url = str(item.get("url", ""))
        if "read.amazon." not in url and "signin" not in url:
            continue
        if "webSocketDebuggerUrl" not in item:
            continue
        targets.append(item)
    return targets


async def wait_for_reader(port: int, timeout_sec: int, poll_sec: float) -> tuple[dict, dict]:
    deadline = time.time() + timeout_sec
    last_seen = []
    while time.time() < deadline:
        for target in candidate_targets(port):
            try:
                async with CdpPage(target["webSocketDebuggerUrl"]) as page:
                    state = await read_state(page)
            except Exception as exc:
                last_seen.append(f"{target.get('url', '')}: {exc}")
                continue
            if state.get("isReader"):
                return target, state
            href = state.get("href") or target.get("url", "")
            status = "reader-not-ready"
            if state.get("isSignIn"):
                status = "sign-in"
            elif state.get("isLibrary"):
                status = "library"
            last_seen.append(f"{href}: {status}")
        await asyncio.sleep(poll_sec)
    detail = "; ".join(last_seen[-5:]) if last_seen else "no Kindle tab found"
    raise RuntimeError(f"Timed out waiting for Kindle reader tab on port {port}: {detail}")


async def connect_reader_page(port: int, timeout_sec: int, poll_sec: float) -> tuple[dict, dict, CdpPage]:
    target, state = await wait_for_reader(port, timeout_sec, poll_sec)
    page = CdpPage(target["webSocketDebuggerUrl"])
    await page.__aenter__()
    return target, state, page


async def export_blob_image(page: CdpPage, output_path: pathlib.Path) -> dict:
    payload = await page.evaluate(EXPORT_BLOB_IMAGE_JS)
    if not isinstance(payload, dict) or "data" not in payload:
        raise RuntimeError(f"Failed to export Kindle page image: {payload}")
    output_path.write_bytes(base64.b64decode(payload["data"]))
    return payload


async def next_button_state(page: CdpPage) -> dict | None:
    geometry = await page.evaluate(NEXT_BUTTON_JS)
    return geometry if isinstance(geometry, dict) else None


async def viewport_state(page: CdpPage) -> dict:
    viewport = await page.evaluate(VIEWPORT_JS)
    if not isinstance(viewport, dict):
        raise RuntimeError("Failed to inspect Kindle viewport state.")
    return viewport


async def move_mouse(page: CdpPage, x: int | float, y: int | float) -> None:
    await page.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})


async def click_mouse(page: CdpPage, x: int | float, y: int | float) -> None:
    await move_mouse(page, x, y)
    await page.call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    await page.call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    )


async def press_key(page: CdpPage, key: str) -> None:
    await page.call(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": key, "windowsVirtualKeyCode": 39 if key == "ArrowRight" else 37},
    )
    await page.call(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": key, "windowsVirtualKeyCode": 39 if key == "ArrowRight" else 37},
    )


async def wait_for_forward_page_advance(
    page: CdpPage,
    previous_page: int | None,
    timeout_sec: float,
    *,
    initial_total_pages: int | None = None,
) -> str:
    if previous_page is None:
        return "unknown"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        await asyncio.sleep(0.5)
        state = await read_state(page)
        current_page = state.get("currentPage")
        direction = page_advance_direction(previous_page, current_page)
        if direction == "forward":
            return "forward"
        if direction == "backward":
            raise RuntimeError(
                f"Reader moved backward after page-turn attempt. Previous page: {previous_page}, current page: {current_page}"
            )
        if numbering_mode_changed(
            previous_page,
            initial_total_pages,
            current_page,
            state.get("totalPages"),
        ):
            return "numbering-mode-changed"
    raise RuntimeError(f"Page did not change after page-turn attempt. Previous page: {previous_page}")


async def turn_page(page: CdpPage, previous_page: int | None, *, timeout_sec: float = 10.0) -> str:
    await page.call("Page.bringToFront")
    initial_state = await read_state(page)
    current_page = initial_state.get("currentPage")
    if previous_page is not None and isinstance(current_page, int) and current_page != previous_page:
        raise PageAlreadyChangedError(
            f"Reader page already changed before click: previous={previous_page}, current={current_page}"
        )

    geometry = await next_button_state(page)
    initial_total_pages = initial_state.get("totalPages")
    if geometry and geometry.get("disabled"):
        raise RuntimeError("Next page button is disabled.")
    if geometry_is_clickable(geometry):
        await click_mouse(page, geometry["x"], geometry["y"])
        result = await wait_for_forward_page_advance(
            page,
            previous_page,
            timeout_sec,
            initial_total_pages=initial_total_pages,
        )
        if result == "numbering-mode-changed":
            await click_mouse(page, geometry["x"], geometry["y"])
            await wait_for_forward_page_advance(page, previous_page, timeout_sec)
        return "cdp-mouse-next-button"

    viewport = await viewport_state(page)
    for probe in hover_probe_points(viewport.get("width", 0), viewport.get("height", 0)):
        await move_mouse(page, probe["x"], probe["y"])
        await asyncio.sleep(0.25)
        geometry = await next_button_state(page)
        if geometry and geometry.get("disabled"):
            raise RuntimeError("Next page button is disabled.")
        if geometry_is_clickable(geometry):
            await click_mouse(page, geometry["x"], geometry["y"])
            result = await wait_for_forward_page_advance(
                page,
                previous_page,
                timeout_sec,
                initial_total_pages=initial_total_pages,
            )
            if result == "numbering-mode-changed":
                await click_mouse(page, geometry["x"], geometry["y"])
                await wait_for_forward_page_advance(page, previous_page, timeout_sec)
            return f"cdp-mouse-next-button-after-{probe['label']}-hover"

    await press_key(page, "ArrowRight")
    await wait_for_forward_page_advance(page, previous_page, timeout_sec)
    return "cdp-key-arrow-right"
