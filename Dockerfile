# syntax=docker/dockerfile:1.7
# map-service-admin — FastAPI 운영 모니터링 백엔드 (cut 1)
#
# hub Dockerfile 의 멀티스테이지 규약을 미러링하되, PostGIS 컴파일
# 의존성(libgeos/libproj, build-essential)은 불필요하므로 제외한다.
# admin 은 hub_data 를 SELECT 만 하고 공간연산을 하지 않으며, psycopg[binary]
# 는 libpq 를 번들하므로 네이티브 빌드 의존성이 없다.

ARG PYTHON_VERSION=3.12

# === builder: 의존성 wheel 사전 빌드 ===
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# === runtime: 최소 실행 이미지 ===
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -m -u 10001 app
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels
# 애플리케이션 소스(템플릿 포함). 소유자를 app:app 로 지정.
COPY --chown=app:app app ./app
USER app
EXPOSE 8000
# /health(app.main:health)가 200 이면 healthy. 표준 라이브러리만 사용.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status==200 else 1)"
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
