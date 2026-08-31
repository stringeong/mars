import os
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    """Raised when deployment settings are unsafe or malformed."""


ENVIRONMENT = os.environ.get("MARS_ENV", "development").strip().lower()
if ENVIRONMENT not in {"development", "test", "production"}:
    raise ConfigurationError("MARS_ENV must be development, test, or production.")

IS_PRODUCTION = ENVIRONMENT == "production"

# JWT 서명 키. 운영 환경에서는 반드시 환경변수로 주입한다.
SECRET_KEY = os.environ.get("MARS_SECRET_KEY", "dev-secret-key-change-me")
_WEAK_SECRET_KEYS = {
    "",
    "dev-secret-key-change-me",
    "change-this-to-a-long-random-secret",
}
if IS_PRODUCTION and (SECRET_KEY in _WEAK_SECRET_KEYS or len(SECRET_KEY) < 32):
    raise ConfigurationError(
        "MARS_SECRET_KEY must be a non-default value of at least 32 characters in production."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("MARS_TOKEN_EXPIRE_MIN", "720"))

DATABASE_URL = os.environ.get("MARS_DATABASE_URL", "sqlite:///./mars.db")
UPLOAD_DIR = Path(os.environ.get("MARS_UPLOAD_DIR", "./uploads")).resolve()

# 워크플로우 생성용 LLM (서버 측). 없으면 규칙 기반 폴백을 사용한다.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MARS_DEFAULT_MODEL", "gemma3:4b")

# 이 시간(초) 동안 하트비트가 없으면 기기를 offline으로 간주하고
# 해당 기기에 할당된 실행 중 작업을 다른 기기로 재할당한다.
HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("MARS_HEARTBEAT_TIMEOUT", "30"))


def _parse_origins(raw: str) -> list[str]:
    origins = [value.strip().rstrip("/") for value in raw.split(",") if value.strip()]
    if any(origin == "*" for origin in origins):
        raise ConfigurationError("MARS_ALLOWED_ORIGINS must not contain a wildcard.")
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
            raise ConfigurationError(
                "MARS_ALLOWED_ORIGINS entries must be HTTP(S) origins without a path."
            )
        if IS_PRODUCTION and parsed.scheme != "https":
            raise ConfigurationError("Production CORS origins must use HTTPS.")
    return origins


_DEFAULT_DEV_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins_raw = os.environ.get("MARS_ALLOWED_ORIGINS", "")
if IS_PRODUCTION and not _allowed_origins_raw.strip():
    raise ConfigurationError("MARS_ALLOWED_ORIGINS is required in production.")
ALLOWED_ORIGINS = _parse_origins(_allowed_origins_raw or _DEFAULT_DEV_ORIGINS)


def _parse_hosts(raw: str) -> list[str]:
    hosts = [value.strip() for value in raw.split(",") if value.strip()]
    if any(host == "*" for host in hosts):
        raise ConfigurationError("MARS_ALLOWED_HOSTS must not contain a wildcard.")
    if any("/" in host or "://" in host for host in hosts):
        raise ConfigurationError("MARS_ALLOWED_HOSTS entries must be hostnames without a scheme or path.")
    return hosts


_DEFAULT_DEV_HOSTS = "localhost,127.0.0.1,testserver"
_allowed_hosts_raw = os.environ.get("MARS_ALLOWED_HOSTS", "")
if IS_PRODUCTION and not _allowed_hosts_raw.strip():
    raise ConfigurationError("MARS_ALLOWED_HOSTS is required in production.")
ALLOWED_HOSTS = _parse_hosts(_allowed_hosts_raw or _DEFAULT_DEV_HOSTS)
