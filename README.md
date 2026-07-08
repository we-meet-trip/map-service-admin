# map-service-admin

MAP 운영 모니터링 백엔드. **cut 1: 읽기전용 운영 모니터링 화면.**

운영자가 브라우저로 여는 모니터링 대시보드(+Swagger)를 제공한다. 클라이언트/프론트엔드가 아니라, admin 서비스가 직접 HTML 화면과 JSON API를 낸다.

대시보드는 라이트 우선(다크 자동, `prefers-color-scheme`) 서버렌더 콘솔이다: 좌측 도메인 레일(상태 점·스크롤스파이) + 전체 상태 히어로 밴드 + KPI 스탯 스트립 + 도메인 카드(플랫폼 서비스 / 기상 파이프라인 / 장소·콘텐츠 / DB 뷰어 / 외부 모니터링). 상태는 항상 글리프+라벨로 표기하며(색 단독 금지), 표는 자체 스크롤로 처리해 모바일에서도 가로 스크롤이 페이지를 넘지 않는다. 템플릿은 공통 `templates/base.html`(디자인 토큰·컴포넌트) 위에 `dashboard.html`·`table.html`이 `extends` 한다.

## 범위 (cut 1)
- **읽기 전용.** hub_data 를 직접 SELECT(읽기전용 역할 `map_admin`) + user/agent/hub 헬스 롤업.
- **다른 레포/스키마 변경 0.** 쓰기 없음. `admin_data`·감사·회원/일정 조회·Agent 잡큐·격자 토글·KMA 강제갱신은 **cut 2**로 연기.
- **경계 준수.** admin 은 어느 스키마에도 쓰지 않고, `user_service` 는 직접 읽지 않는다(cut 2에서 user-BFF 위임). SoT §8.1의 hub_data 읽기전용 예외만 사용.

## 엔드포인트
| 경로 | 인증 | 설명 |
|---|---|---|
| `GET /` | Basic | HTML 대시보드(폴링/예보/장소/헬스) |
| `GET /docs`, `/openapi.json` | Basic | Swagger UI |
| `GET /api/ops/polling` | Basic | 활성/전체 격자, 예보별 최신 발표·행수 |
| `GET /api/ops/forecast-rows` | Basic | 예보 3테이블 행수·만료 |
| `GET /api/ops/places-stats` | Basic | 장소 출처별 집계 |
| `GET /api/ops/health` | Basic | user/agent/hub 헬스 롤업 |
| `GET /api/ops/gemini` | Basic | Gemini 연결 상태(models.list, 무료 메타 호출) |
| `GET /api/ops/monitoring` | Basic | 외부 모니터링 연동 슬롯 목록(Grafana 등, config 기반) |
| `GET /api/db/tables` | Basic | hub_data 테이블 목록 + 행수 |
| `GET /api/db/tables/{table}` | Basic | hub_data 테이블 행 페이지네이션(JSON) |
| `GET /db/{table}` | Basic | hub_data 테이블 행 브라우저(HTML) |
| `GET /health` | 없음 | liveness(compose healthcheck) |

> **DB 뷰어 범위**: `hub_data` 스키마 테이블만. `user_service`(PII)·`langgraph`(SDK 전용)는 제외 — `map_admin` 권한과 테이블명 화이트리스트로 이중 차단(미허용 테이블 요청 시 404).
> **Gemini**: agent 소유 모델이지만 admin 이 `GEMINI_API_KEY`(공유 .env)로 연결/키 유효성만 점검. 생성 호출 없음(quota 무소모). 키 미설정 시 "미설정" 표시.

## 외부 모니터링 연동 (Grafana 등)

대시보드 하단 "외부 모니터링" 섹션은 이미 운영 중인 모니터링 도구(Grafana·Prometheus 등)를 화면에 **연결(link)** 하는 config-only 슬롯이다. **admin 은 해당 도구를 직접 기동하지 않는다**(infra·SoT·타 레포 무변경, cut 1 유지). `env MONITORING_PANELS` 에 JSON 배열로 지정한다:

```
MONITORING_PANELS=[{"title":"Grafana · MAP 개요","url":"http://127.0.0.1:3000/d/UID/map?kiosk&refresh=30s","embed":true,"height":460,"description":"서비스 지표 개요"},{"title":"Prometheus","url":"http://127.0.0.1:9090","embed":false}]
```

- `embed:true` → 대시보드에 `<iframe>` 인라인 임베드(전폭). 대상이 프레임 삽입을 허용해야 보인다(예: Grafana `grafana.ini [security] allow_embedding=true`). `X-Frame-Options`/CSP `frame-ancestors` 로 차단되면 임베드가 비어 보일 수 있어, 각 패널에 항상 "새 탭에서 열기 ↗" 링크와 폴백 안내를 함께 제공한다.
- `embed:false` → 새 탭 링크 카드로만 노출.
- `url` 은 http/https 만 허용(`javascript:` 등 iframe src 주입 차단). `height` 는 120–2000px 로 보정.
- 미설정(빈 배열)이면 "아직 연동된 모니터링이 없습니다" 안내 + 설정 예시를 표시한다.
- JSON 은 `GET /api/ops/monitoring` 으로도 조회할 수 있다.

## 인증
단일 공유 **HTTP Basic**(`ADMIN_BASIC_USER`/`ADMIN_BASIC_PASSWORD`, .env). 계정 테이블/bcrypt/세션 없음. loopback 바인딩 전제 하에 평문 Basic 허용.

## 실행 (map-service-infra 경유)
admin 은 infra 의 `docker-compose.yml` 에 서비스로 편입되어 있고 공유 `./.env` 를 읽는다. host `127.0.0.1:8002` → 컨테이너 8000.

```bash
# 1) infra/.env 에 admin 키 추가 (map-service-admin/.env.example 참고)
#    ADMIN_DATABASE_URL / ADMIN_BASIC_USER / ADMIN_BASIC_PASSWORD / MAP_ADMIN_PASSWORD / USER_BASE_URL
# 2) map_admin 읽기전용 역할 생성 — db/init/10-admin.sh
#    · 새 볼륨: postgres 최초 기동 시 자동 실행됨
#    · 기존 볼륨: 아래처럼 1회 수동 적용(초기화 스크립트는 최초 부팅에만 자동 실행)
docker compose --profile full up -d postgres
docker compose exec postgres bash /docker-entrypoint-initdb.d/10-admin.sh
# 3) 전체 기동
docker compose --profile full up -d --build
# 4) 브라우저로 http://127.0.0.1:8002/ (Basic 로그인)
```

## 검증
- `GET /health` → 200.
- Basic 없이 `/api/ops/*`·`/docs` → 401. 올바른 Basic → 200.
- `/api/ops/polling` 값이 `psql`로 본 `hub_data.subscribed_grids` 등과 일치.
- 헬스 롤업이 user(`/actuator/health`)·agent·hub(`/health`) up/down 표시.
- 단위 테스트: `pytest`(`tests/test_smoke.py` — DB 불필요 경로).

> 빈/키 없는 환경에서는 예보·폴링이 비어 있을 수 있다(KMA_SERVICE_KEY 미설정 시). 화면은 "데이터 없음" 으로 표시한다.
