"""map-service-admin 환경설정 (cut 2 — 운영 콘솔 JSON API).

다른 서비스(user/agent/hub)와 동일한 프로젝트 루트 `.env` 를 공유하므로
`extra="ignore"` 로 무관한 키를 무시한다(hub/config.py 와 동일 규약).

cut 2 범위: hub_data 읽기전용 + admin_data 소유 RW(감사/계정/세션) + Redis 진단
RO(DB2 스트림·DB3 Gemini 쿼터·DB4 캐시) + hub/BFF `/internal` 위임 + 외부 API
상태/프로브. 인증은 admin_accounts(bcrypt) + 서버측 세션(HttpOnly 쿠키).
"""
from __future__ import annotations

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitoringPanel(BaseModel):
    """외부 모니터링 연동 패널 1개(Grafana·Prometheus 등 범용).

    admin 은 대상 도구를 iframe/링크로 '연결'만 한다(직접 기동은 compose
    monitoring 프로파일이 담당). SPA 의 모니터링 화면이 본 슬롯을 렌더한다.
    """

    title: str
    url: str
    embed: bool = False
    height: int = 420
    description: str | None = None

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        """http/https 스킴만 허용(javascript: 등 iframe src 주입 차단)."""
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("MONITORING_PANELS url must be http(s)")
        return v

    @field_validator("height")
    @classmethod
    def _sane_height(cls, v: int) -> int:
        """iframe 높이를 상식 범위(120–2000px)로 보정."""
        return max(120, min(v, 2000))


class Settings(BaseSettings):
    """환경변수/`.env` 기반 설정."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # [DB] map_admin DSN. hub_data SELECT + admin_data 소유 RW.
    ADMIN_DATABASE_URL: str
    # 쿼리 statement timeout(초). 엔진 connect_args 에 반영(느린 조회 상한).
    DB_TIMEOUT_SEC: float = 5.0

    # [인증 — 계정 세션] admin_accounts(bcrypt) + admin_sessions(HttpOnly 쿠키).
    # 최초 계정 시드: accounts 가 비었을 때만 아래 부트스트랩 자격으로 1회 생성.
    ADMIN_BOOTSTRAP_USER: str = ""
    ADMIN_BOOTSTRAP_PASSWORD: SecretStr = SecretStr("")
    ADMIN_SESSION_COOKIE_NAME: str = "admin_session"
    ADMIN_SESSION_TTL_MIN: int = 720  # 12h
    # 터널(HTTPS) 배포 시 True. loopback dev 는 False(쿠키 전송 허용).
    ADMIN_SESSION_COOKIE_SECURE: bool = False

    # [CORS] dev SPA origin 목록(JSON 배열 또는 콤마구분). 프로덕션은 nginx
    # same-origin 프록시라 비워 둔다. 세션 쿠키를 위해 allow_credentials=True.
    ADMIN_CORS_ORIGINS: list[str] = []

    # [헬스 롤업 대상 — 컨테이너 내부 포트]
    USER_BASE_URL: str = "http://user:8080"
    AGENT_BASE_URL: str = "http://agent:8000"
    HUB_BASE_URL: str = "http://hub:8000"
    HEALTH_TIMEOUT_SEC: float = 3.0

    # [OSRM 프로브] hub 와 동일 키 재사용. 비면 프로브 skip.
    OSRM_FOOT_BASE_URL: str = ""
    OSRM_BICYCLE_BASE_URL: str = ""

    # [Redis 진단 RO] 스트림/쿼터/캐시 조회. hub/BFF 와 동일 인스턴스.
    ADMIN_REDIS_URL: str = "redis://redis:6379"
    REDIS_DB_STREAMS: int = 2
    REDIS_DB_RATELIMIT: int = 3
    REDIS_DB_CACHE: int = 4
    # 스트림/DLQ/컨슈머 이름(agent·BFF 규약과 일치).
    STREAM_DONE: str = "agent:jobs:done"
    STREAM_STATUS: str = "agent:jobs:status"
    STREAM_DLQ: str = "agent:jobs:done:dlq"
    STREAM_GROUP: str = "bff-result"
    REDIS_TIMEOUT_SEC: float = 2.0

    # [내부 위임] hub/BFF `/internal` 아웃바운드 토큰(공유 비밀 재사용).
    INTERNAL_SERVICE_TOKEN: SecretStr = SecretStr("")
    INTERNAL_TIMEOUT_SEC: float = 5.0

    # [Gemini 연결 점검] 무료 메타 호출(models.list). 생성 미사용.
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODELS_URL: str = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )
    GEMINI_TIMEOUT_SEC: float = 5.0
    GEMINI_RPD_CAP: int = 200  # agent 의 일일 쿼터 상한(표시용)

    # [외부 API 키 존재 여부/프로브] hub 소유 키를 공유 .env 에서 읽어 상태
    # 표시·수동 프로브에 사용한다. 값은 마스킹해서만 노출한다.
    KAKAO_REST_API_KEY: SecretStr = SecretStr("")
    KMA_SERVICE_KEY: SecretStr = SecretStr("")
    TOUR_API_SERVICE_KEY: SecretStr = SecretStr("")
    NAVER_CLIENT_ID: SecretStr = SecretStr("")
    NAVER_CLIENT_SECRET: SecretStr = SecretStr("")
    EXTERNAL_PROBE_TIMEOUT_SEC: float = 6.0

    # [DB 뷰어(hub_data 한정)]
    DB_PAGE_SIZE_DEFAULT: int = 50
    DB_PAGE_SIZE_MAX: int = 500
    DB_EXPORT_MAX_ROWS: int = 50000

    # [외부 모니터링 연동 슬롯] Grafana 등 iframe/링크. JSON 배열.
    MONITORING_PANELS: list[MonitoringPanel] = []


# 프로세스 단위 싱글톤. 다른 모듈은 이 객체를 직접 임포트한다.
settings = Settings()
