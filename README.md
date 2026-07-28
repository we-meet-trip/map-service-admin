# map-service-admin

MAP 운영 콘솔 백엔드. **cut 2: 순수 JSON API 서버.**

운영 콘솔 UI 는 별도 SPA(`web/`, React/Vite → nginx)가 담당하고, 본 서비스는
그 SPA 가 소비하는 `/api/v1/*` JSON API 만 제공한다(HTML/Jinja2 없음). 인증은
`admin_data.admin_accounts`(bcrypt) + 서버측 세션(HttpOnly 쿠키)이다 — 초기
cut 1 의 "단일 공유 HTTP Basic" 안은 폐기되었다.

## 데이터 경로 / 경계 (SoT B9)

- **hub_data** — 읽기전용 직접 SELECT(역할 `map_admin`). DB 뷰어·폴링/예보/장소 집계.
- **admin_data** — admin 소유 RW. `audit_logs`·`admin_accounts`·`admin_sessions`. Alembic 관리.
- **Redis 진단 RO** — DB2 스트림/DLQ/PEL · DB3 Gemini 쿼터 · DB4 캐시 키수(값 미접근).
- **hub `/internal` 위임** — KMA 강제갱신·격자 토글·금지구역 CRUD(hub_data 쓰기는 hub 소유).
- **user-BFF `/internal/admin` 위임** — 회원 조회·추천작업/DLQ(user_service 직접 grant 없음).

모든 쓰기·민감읽기는 소유 서비스 `/internal` 로 위임한다. admin 은 hub_data 에
쓰지 않으며(권한 계층에서도 SELECT-only), user_service 를 직접 읽지 않는다.

## 엔드포인트 (`/api/v1`)

| 경로 | 인증 | 설명 |
|---|---|---|
| `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` | 세션 | 로그인/로그아웃/현재 운영자 |
| `GET /ops/overview` | 세션 | 대시보드 집계(헬스+폴링+Gemini쿼터+스트림) |
| `GET /ops/health` | 세션 | 서비스+인프라+OSRM 헬스 롤업(postgres/redis 포함) |
| `GET /ops/polling` · `/ops/forecast-rows` · `/ops/places-stats` | 세션 | hub_data 운영 지표 |
| `GET /ops/gemini` | 세션 | Gemini 연결 + 일일 쿼터(Redis DB3) |
| `GET /ops/streams` | 세션 | 잡 스트림/DLQ/PEL 요약(Redis DB2) |
| `GET /ops/external` | 세션 | 외부 API 6종 상태(configured/캐시/쿼터, 라이브 호출 없음) |
| `POST /ops/external/{provider}/probe` | 세션 | 외부 API 수동 프로브(1회, audit 기록) |
| `GET /ops/monitoring` | 세션 | Grafana 등 연동 슬롯(MONITORING_PANELS) |
| `GET /db/tables` · `/db/tables/{t}/schema` · `/db/tables/{t}` | 세션 | 테이블 목록/스키마/행(정렬·검색·필터) |
| `GET /db/tables/{t}/export.csv` | 세션 | 현재 필터/정렬 반영 CSV |
| `GET /users` · `/users/{id}` | 세션 | 회원 목록(마스킹)/상세(원문, 열람 audit) — BFF 위임 |
| `GET /jobs/stats` · `/jobs` · `/jobs/dlq` | 세션 | 추천작업 통계/목록/DLQ — BFF 위임 |
| `POST /actions/kma/run-now` | 세션 | KMA 강제갱신 — hub 위임(+audit) |
| `PATCH /actions/grids/{id}` | 세션 | 폴링 격자 토글 — hub 위임(+audit before/after) |
| `GET/POST/PUT/DELETE /actions/forbidden-zones[/{id}]` | 세션 | 금지구역 CRUD — hub 위임(+audit) |
| `POST /actions/dlq/reprocess` · `/dlq/discard` | 세션 | DLQ 재처리/폐기 — BFF 위임(+audit) |
| `GET /audit` | 세션 | 감사 로그 조회(actor/action/from/to 필터) |
| `GET /metrics` | 없음 | Prometheus 계측(map-net 내부 스크레이프) |
| `GET /health` | 없음 | liveness(compose healthcheck) |
| `GET /docs` · `/openapi.json` | 세션 | Swagger UI |

> **DB 뷰어 범위**: `hub_data` 만. `user_service`(PII)·`langgraph` 는 제외 —
> `map_admin` 권한 + 테이블명 화이트리스트로 이중 차단(미허용 404). 정렬/필터
> 컬럼은 카탈로그와 대조 검증(무효 시 422), geometry 는 `ST_AsText` 로 요약.
> **외부 API 프로브**: KMA/Kakao/Naver/Durunubi 는 실쿼터를 소모하므로 GET 자동
> 폴링에 섞지 않고 명시적 POST 프로브로만 수행하며 audit 를 남긴다. 키 값은 마스킹만.

## 인증

`admin_data.admin_accounts`(bcrypt) + `admin_data.admin_sessions`(HttpOnly·
SameSite=Lax 쿠키). 최초 계정은 기동 시 `ADMIN_BOOTSTRAP_USER`/
`ADMIN_BOOTSTRAP_PASSWORD` 로 1회 시드(테이블이 비어 있을 때만). 감사 로그의
actor 가 세션 운영자 username 이다.

## 마이그레이션

`admin_data` 스키마·테이블은 admin 레포 Alembic(hub 의 raw-SQL 스타일)이
소유·관리한다. 컨테이너 엔트리포인트(`entrypoint.sh`)가 uvicorn 기동 전
`alembic upgrade head` 를 실행한다. `map_admin` 이 `admin_data` 를 소유하도록
infra `db/init/10-admin.sh` 가 `ALTER SCHEMA admin_data OWNER TO map_admin` 을
수행한다(새 볼륨 자동, 기존 볼륨은 수동 1회).

## 실행 (map-service-infra 경유)

admin(8002 API) + admin-web(8003 SPA)은 infra `docker-compose.yml` 에 편입되어
공유 `./.env` 를 읽는다.

```bash
# 1) infra/.env 에 admin 키 추가 (.env.example 참고): ADMIN_DATABASE_URL /
#    ADMIN_BOOTSTRAP_USER/PASSWORD / MAP_ADMIN_PASSWORD / INTERNAL_SERVICE_TOKEN /
#    ADMIN_REDIS_URL / OSRM_*_BASE_URL / USER_BASE_URL / (외부 API 키)
# 2) map_admin 역할 + admin_data 소유 — db/init/10-admin.sh
#    · 새 볼륨: postgres 최초 기동 시 자동
#    · 기존 볼륨: docker compose exec postgres bash /docker-entrypoint-initdb.d/10-admin.sh
docker compose --profile full up -d --build
# 3) 브라우저로 http://127.0.0.1:8003/ (SPA 로그인)
#    API 직접: http://127.0.0.1:8002/api/v1/... (세션 쿠키 필요)
```

### SPA (web/) 개발

```bash
cd web && npm install && npm run dev   # Vite dev(:5173), /api → 127.0.0.1:8002 프록시
npm run build                          # 프로덕션 정적 빌드(nginx 이미지가 서빙)
```

## 검증

- `GET /health` → 200(인증 없음). 세션 없이 `/api/v1/*` → 401.
- 로그인 → 세션 쿠키 발급 → `/api/v1/auth/me` 200. 로그아웃 후 401.
- `/ops/health` 롤업에 postgres/redis/osrm 포함.
- 격자 토글/KMA 강제갱신/DLQ 재처리 → `audit_logs` 1행 + `/api/v1/audit` 노출.
- 단위 테스트: `pytest`(`tests/test_smoke.py` — DB/Redis/업스트림 모킹).
