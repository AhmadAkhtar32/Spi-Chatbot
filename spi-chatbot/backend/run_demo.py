"""Run the prepared internal demo through one frontend/backend address."""

import argparse
import logging
import logging.config
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent.parent / "spi-chatbot-react" / "dist"
PUBLISHED_DIR = BACKEND_DIR / "published_demo"


def background_log_config():
    folder = BACKEND_DIR / "logs"
    folder.mkdir(parents=True, exist_ok=True)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            },
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard",
                "filename": str(folder / "demo-server.log"),
                "maxBytes": 2 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "root": {
            "handlers": ["file"],
            "level": "INFO",
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["file"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": [],
                "level": "INFO",
                "propagate": True,
            },
            "uvicorn.access": {
                "handlers": ["file"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }


class DemoFrontend(StaticFiles):
    async def get_response(self, path, scope):
        if scope["method"] in {"GET", "HEAD"} and path.strip("/") in {
            "settings", "help",
        }:
            path = "index.html"

        response = await super().get_response(path, scope)

        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"

        return response


def main():
    parser = argparse.ArgumentParser(
        description="Start the internal SPIA demo"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")

    log_config = background_log_config() if args.background else None

    if log_config is not None:
        logging.config.dictConfig(log_config)

    def report(message):
        if args.background:
            logging.getLogger("spia.startup").info(message)
        else:
            print(message, flush=True)

    load_dotenv(BACKEND_DIR / ".env", override=True)

    if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
        raise RuntimeError(
            "Set ENABLE_DEMO_SESSIONS=1 in backend/.env"
        )

    if os.environ.get("BUSINESS_DATA_SOURCE", "demo_json") != "demo_json":
        raise RuntimeError(
            "This demo launcher requires BUSINESS_DATA_SOURCE=demo_json"
        )

    if not (FRONTEND_DIR / "index.html").is_file():
        raise RuntimeError(
            "Build the React frontend before starting this launcher"
        )

    os.environ["SPIA_PUBLISHED_DIR"] = str(PUBLISHED_DIR)

    from published_knowledge import EXPERTS, get_published

    for expert in EXPERTS:
        knowledge = get_published(expert)
        report(
            f"READY: {expert}; "
            f"{len(knowledge.chunks)} published sections"
        )

    os.chdir(BACKEND_DIR)

    from app import app

    app.router.routes[:] = [
        route for route in app.router.routes
        if not (
            isinstance(route, Mount)
            and route.path == ""
            and route.name == "frontend"
        )
    ]

    app.mount(
        "/",
        DemoFrontend(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )

    import uvicorn

    display_host = (
        "127.0.0.1" if args.host == "0.0.0.0" else args.host
    )
    report(f"Open http://{display_host}:{args.port}")

    options = {"log_config": log_config} if args.background else {}

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        **options,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        if "--background" in sys.argv:
            logging.getLogger("spia.startup").exception("Startup failed")
        raise SystemExit(f"STARTUP FAILED: {exc}") from None