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

# localhost 외에 같은 공유기 안의 다른 기기(사설 IP 대역)에서 여는 웹도 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):\d+"
    ),
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
