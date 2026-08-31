# 운영 HTTPS 배포 가이드

이 구성은 브라우저와 외부 Worker가 Nginx의 HTTPS endpoint만 사용하고, FastAPI 컨테이너는 Docker 내부 네트워크에서만 접근하도록 한다. 인증서는 호스트에서 발급·갱신한 PEM 파일을 읽기 전용으로 마운트한다.

## 1. DNS와 인증서 준비

운영 도메인(예: `mars.example.com`)을 서버로 연결하고 Let's Encrypt 등 신뢰할 수 있는 CA에서 인증서를 발급한다. 다음 두 파일의 실제 호스트 경로가 필요하다.

- certificate chain: `fullchain.pem`
- private key: `privkey.pem`

비밀키와 TLS private key를 저장소에 복사하거나 커밋하지 않는다. 애플리케이션은 설정 오류에 비밀값 자체를 출력하지 않는다.

## 2. 운영 환경변수

`.env`에는 최소한 다음 값을 설정한다.

```dotenv
MARS_ENV=production
MARS_SECRET_KEY=<openssl-rand-hex-32 결과>
MARS_ALLOWED_ORIGINS=https://mars.example.com
MARS_ALLOWED_HOSTS=mars.example.com
MARS_TLS_CERT_FILE=/etc/letsencrypt/live/mars.example.com/fullchain.pem
MARS_TLS_KEY_FILE=/etc/letsencrypt/live/mars.example.com/privkey.pem
MARS_HTTP_PORT=80
MARS_HTTPS_PORT=443
```

`MARS_SECRET_KEY`는 32자 이상이어야 하며 기본 예시 값은 거부된다. Origin과 Host의 `*` wildcard도 거부되고, 운영 Origin은 HTTPS만 허용된다. 여러 값은 쉼표로 구분한다.

## 3. 기동과 확인

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -I http://mars.example.com/
curl https://mars.example.com/api/
```

HTTP 요청은 HTTPS로 `308` 리다이렉트되어야 한다. HTTPS 응답에는 HSTS, CSP, `X-Content-Type-Options`, Referrer Policy와 Permissions Policy가 포함된다. 운영에서는 `/docs`, `/redoc`, `/openapi.json`이 비활성화된다.

호스트 방화벽에는 80/443만 공개한다. FastAPI 8000 포트는 production override에서 제거되며, 기본 개발 Compose에서도 `127.0.0.1`에만 바인딩된다. Worker UI와 Ollama 포트 역시 localhost 바인딩을 유지한다.

## 4. API 경계와 Worker 연결

- 브라우저: `https://mars.example.com`, API는 same-origin `/api` 사용
- 사용자 API: JWT Bearer 인증
- Worker API: `X-Device-Key` 인증
- 같은 Compose의 Worker: `http://server:8000`
- 외부 Worker: `https://mars.example.com/api`

외부 Worker는 서버의 8000 포트에 직접 연결하지 않는다.

## 5. 인증서 갱신

호스트에서 인증서를 갱신한 뒤 Nginx 컨테이너를 재생성해 새 파일을 읽게 한다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate web
```
