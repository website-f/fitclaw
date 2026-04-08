from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["web-app"])

PWA_DIR = Path(__file__).resolve().parents[1] / "ui" / "pwa"
NO_CACHE_HTML_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}
NO_CACHE_SW_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Service-Worker-Allowed": "/"}


@router.get("/app", include_in_schema=False)
def chat_app():
    return FileResponse(PWA_DIR / "chat_app.html", media_type="text/html", headers=NO_CACHE_HTML_HEADERS)


@router.get("/transit-live", include_in_schema=False)
def transit_live_app():
    return FileResponse(PWA_DIR / "transit_live.html", media_type="text/html", headers=NO_CACHE_HTML_HEADERS)


@router.get("/app-manifest.webmanifest", include_in_schema=False)
def app_manifest():
    return FileResponse(
        PWA_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/app-sw.js", include_in_schema=False)
def app_service_worker():
    return FileResponse(PWA_DIR / "service-worker.js", media_type="application/javascript", headers=NO_CACHE_SW_HEADERS)
