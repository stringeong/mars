from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import ALLOWED_HOSTS, ALLOWED_ORIGINS, IS_PRODUCTION
from .database import Base, engine
from .routers import auth, devices, executions, files, services, worker

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="M.A.R.S",
    description="MAS And Resource Sharing — 개인 멀티 디바이스 AI 서비스 플랫폼",
    version="0.1.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(services.router)
app.include_router(executions.router)
app.include_router(files.router)
app.include_router(worker.router)


@app.get("/")
def root():
    return {"service": "M.A.R.S", "status": "ok"}
