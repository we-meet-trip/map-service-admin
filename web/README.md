# MAP 운영 콘솔 (map-admin-web)

MAP 백엔드 운영자용 관리 콘솔 SPA. `map-service-admin` JSON API를 소비하는 읽기 우선 대시보드이며, 모든 쓰기 액션은 확인 다이얼로그를 거쳐 서버 측 감사 로그에 기록됩니다.

## 기술 스택

- React 18 + TypeScript (strict)
- Vite 5 (빌드 · dev 서버)
- React Router v6 (`createBrowserRouter`)
- TanStack Query v5 (데이터 패칭 · 캐시)
- Tailwind CSS 3.4 (PostCSS + autoprefixer)
- Recharts (개요 차트)

의존성은 모두 고정 버전으로 핀되어 있습니다. 외부 아이콘/UI 라이브러리 없이 인라인 SVG와 자체 컴포넌트로 구성됩니다.

## 개발 (dev)

```bash
npm install
npm run dev
```

- dev 서버: <http://localhost:5173>
- `/api` 요청은 `vite.config.ts`의 프록시가 로컬 admin API(`http://127.0.0.1:8002`)로 전달합니다.
- admin API를 로컬에서 함께 띄워야 로그인/데이터 호출이 동작합니다. dev 교차출처 세션 쿠키를 위해 admin `.env`에 `ADMIN_CORS_ORIGINS=["http://localhost:5173"]`, `ADMIN_SESSION_COOKIE_SECURE=false`가 필요합니다.

## 빌드

```bash
npm run build      # tsc 타입체크 후 vite 프로덕션 빌드 → dist/
npm run preview    # 빌드 결과 로컬 미리보기 (:5173)
npm run typecheck  # 타입 검사만
```

## 프로덕션 서빙 (compose)

프로덕션은 nginx가 정적 빌드를 서빙하고, 같은 오리진의 `/api/`를 admin 컨테이너(`admin:8000`)로 프록시합니다. 세션 쿠키(`admin_session`, HttpOnly)는 same-origin이므로 그대로 전달됩니다.

```bash
docker build -t map-admin-web .
```

- `Dockerfile`: `node:22-alpine`에서 `npm ci && npm run build` → `nginx:alpine`에 `dist/`와 `nginx.conf` 복사. arm64(라즈베리파이 4) 호환.
- `nginx.conf`:
  - `location /api/` → `proxy_pass http://admin:8000;`
  - `location /` → `try_files $uri /index.html;` (SPA 폴백)

`map-service-infra`의 docker-compose에서 이 이미지를 서비스로 추가하고 admin과 같은 네트워크(map-net)에 두면 됩니다.

## 인증 흐름

- 모든 요청은 `credentials: 'include'`로 세션 쿠키를 전송합니다.
- 부팅 시 `GET /api/v1/auth/me`로 세션을 확인합니다. 401이면 `/login`으로 이동합니다.
- 임의 요청이 401을 반환하면 전역 핸들러가 세션을 비우고 `/login`으로 리다이렉트합니다.

## 구조

```
src/
  api/         client(fetch 래퍼) · endpoints · types
  app/         router · RootLayout · RequireAuth · nav
  components/  재사용 UI (DataTable, StatTile, StatusPill, ConfirmDialog 등)
  components/layout/  AppLayout · Sidebar · TopBar
  providers/   Auth · Theme · Toast · Confirm
  pages/       Overview · External · Weather · Places · Users · Jobs · Db · Audit · Monitoring · Login
  lib/         format · status · cn
```

## 디자인

- 라이트 우선 + 자동 다크(`prefers-color-scheme`) + 수동 토글(`data-theme`, localStorage 영속).
- 상태 색상(정상/주의/경고/중단)은 항상 텍스트 라벨 또는 아이콘과 함께 표기합니다(색상 단독 사용 금지).
