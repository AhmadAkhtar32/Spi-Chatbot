"""API composition; security and services have separate responsibilities."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spia.core.paths import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env", override=True)

from spia.api.access import router as access_router
from spia.api.business import router as business_router
from spia.api.experts import router as expert_router
from spia.api.documents import router as document_router

from spia.security.request_guard import install_request_guard

app = FastAPI(
    title="SPIA Assistant API",
    version="1.0.0",
)

origins = [
    value.strip()
    for value in os.environ.get(
        "SPIA_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if value.strip()
]

if "*" in origins:
    raise RuntimeError(
        "Configure explicit SPIA_ALLOWED_ORIGINS"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=['Authorization', 'Content-Type', 'X-SPIA-Question'],
)

app.include_router(access_router)
app.include_router(business_router)
app.include_router(expert_router)
app.include_router(document_router)


install_request_guard(app)
