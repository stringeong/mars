import os

# JWT 서명 키. 운영 환경에서는 반드시 환경변수로 주입한다.
# (HS256 권장 최소 길이 32바이트 이상 — 짧으면 브루트포스에 취약)
SECRET_KEY = os.environ.get(
    "MARS_SECRET_KEY", "dev-only-secret-key-change-me-in-production-0123456789"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("MARS_TOKEN_EXPIRE_MIN", "720"))

DATABASE_URL = os.environ.get("MARS_DATABASE_URL", "sqlite:///./mars.db")

# 워크플로우 생성용 LLM (서버 측). 없으면 규칙 기반 폴백을 사용한다.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MARS_DEFAULT_MODEL", "gemma3:4b")

# 이 시간(초) 동안 하트비트가 없으면 기기를 offline으로 간주하고
# 해당 기기에 할당된 실행 중 작업을 다른 기기로 재할당한다.
HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("MARS_HEARTBEAT_TIMEOUT", "30"))
