from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import auth, devices, executions, services, worker

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="M.A.R.S",
    description="MAS And Resource Sharing — 개인 멀티 디바이스 AI 서비스 플랫폼",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(services.router)
app.include_router(executions.router)
app.include_router(worker.router)


@app.get("/")
def root():
    return {"service": "M.A.R.S", "status": "ok"}
