"""map-service-admin 환경설정.

운영 모니터링 백엔드(cut 1)의 설정 컨테이너. 다른 서비스(user/agent/hub)와
동일한 프로젝트 루트 `.env` 를 공유하므로 `extra="ignore"` 로 무관한 키를
무시한다(hub/config.py 와 동일 규약).

cut 1 범위: hub_data 읽기전용 조회 + user/agent/hub 헬스 롤업.
쓰기·admin_data·감사·회원조회는 cut 2로 연기.

호출처:
  - app.db        — ADMIN_DATABASE_URL (map_admin 읽기전용 DSN)
  - app.security  — ADMIN_BASIC_USER / ADMIN_BASIC_PASSWORD (단일 공유 Basic)
  - app.health_client — USER/AGENT/HUB_BASE_URL, HEALTH_TIMEOUT_SEC
"""
from __future__ import annotations

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitoringPanel(BaseModel):
    """외부 모니터링 연동 패널 1개(Grafana·Prometheus 등 범용).

    admin 은 Grafana/Prometheus 를 **직접 기동하지 않는다**(cut 1 무변경).
    운영자가 이미 띄워 둔 모니터링 URL 을 env 로 '연결'하기 위한 슬롯이다.

    필드:
      title       : 패널 표시명(예: "Grafana · MAP 개요").
      url         : 대상 URL. http/https 만 허용(iframe/링크 안전).
      embed       : True 면 대시보드에 <iframe> 인라인 임베드, False 면
                    새 탭 링크 카드로만 노출. (임베드는 대상이 프레임 삽입을
                    허용해야 보인다 — Grafana allow_embedding 등.)
      height      : embed=True 일 때 iframe 높이(px).
      description : 카드 하단 보조 설명(선택).
    """

    title: str
    url: str
    embed: bool = False
    height: int = 420
    description: str | None = None

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        """http/https 스킴만 허용(javascript: 등 iframe src 주입 차단).

        스킴은 RFC 3986 상 대소문자 무시이므로 소문자로 접어 비교한다
        (`HTTPS://` 도 유효 — 원본 v 는 그대로 반환)."""
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("MONITORING_PANELS url must be http(s)")
        return v

    @field_validator("height")
    @classmethod
    def _sane_height(cls, v: int) -> int:
        """iframe 높이를 상식 범위(120–2000px)로 보정."""
        return max(120, min(v, 2000))


class Settings(BaseSettings):
    """환경변수/`.env` 기반 설정.

    [필수]
    ADMIN_DATABASE_URL: SQLAlchemy 비동기 DSN. map_admin(읽기전용) 역할로
        hub_data 를 SELECT 한다. 예:
        postgresql+psycopg://map_admin:<pw>@postgres:5432/map
        (<pw> 는 infra .env 의 MAP_ADMIN_PASSWORD 와 반드시 일치)

    [운영자 인증 — 단일 공유 HTTP Basic]
    ADMIN_BASIC_USER / ADMIN_BASIC_PASSWORD: 대시보드·/docs·API 공통 Basic
        자격. 계정 테이블/bcrypt 없이 .env 한 쌍으로 단순 운영(현 단계 간단히).

    [헬스 롤업 대상 — 컨테이너 내부 포트]
    USER_BASE_URL: Spring user-BFF (헬스는 /actuator/health).
    AGENT_BASE_URL / HUB_BASE_URL: FastAPI (헬스는 /health).
        map-net 안에서는 컨테이너명+컨테이너포트(user:8080, agent:8000,
        hub:8000)로 도달한다(호스트 매핑 8001 아님).
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ADMIN_DATABASE_URL: str

    ADMIN_BASIC_USER: str = "admin"
    ADMIN_BASIC_PASSWORD: SecretStr = SecretStr("")

    USER_BASE_URL: str = "http://user:8080"
    AGENT_BASE_URL: str = "http://agent:8000"
    HUB_BASE_URL: str = "http://hub:8000"

    HEALTH_TIMEOUT_SEC: float = 3.0
    DB_TIMEOUT_SEC: float = 5.0

    # [Gemini 연결 점검] agent 소유 모델이지만, admin 은 연결+키 유효성만
    # 무료 메타 호출(models.list)로 점검한다. 생성(generateContent) 미사용.
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODELS_URL: str = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )
    GEMINI_TIMEOUT_SEC: float = 5.0

    # [DB 뷰어(hub_data 한정)] 페이지네이션 기본/상한
    DB_PAGE_SIZE_DEFAULT: int = 50
    DB_PAGE_SIZE_MAX: int = 500

    # [외부 모니터링 연동 슬롯] Grafana·Prometheus 등 이미 운영 중인 모니터링
    # URL 을 대시보드에 '연결'하기 위한 config-only 슬롯. admin 은 해당 도구를
    # 직접 기동하지 않는다(cut 1 무변경). env 에 JSON 배열로 지정한다. 예:
    #   MONITORING_PANELS=[{"title":"Grafana · MAP 개요",
    #     "url":"http://grafana:3000/d/uid/map?kiosk","embed":true,"height":460,
    #     "description":"서비스 지표 개요"}]
    # 미설정(빈 배열)이면 화면은 "연동된 모니터링 없음" 안내를 표시한다.
    # pydantic-settings 는 복합 타입 env 값을 JSON 으로 자동 파싱한다.
    MONITORING_PANELS: list[MonitoringPanel] = []


# 프로세스 단위 싱글톤. 다른 모듈은 이 객체를 직접 임포트한다.
settings = Settings()
