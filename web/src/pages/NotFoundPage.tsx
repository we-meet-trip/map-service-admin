import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
      <p className="text-5xl font-bold text-fg-subtle">404</p>
      <div>
        <h1 className="text-lg font-semibold text-fg">페이지를 찾을 수 없습니다</h1>
        <p className="mt-1 text-sm text-fg-muted">
          요청하신 경로가 존재하지 않습니다.
        </p>
      </div>
      <Link to="/" className="btn btn-primary">
        개요로 이동
      </Link>
    </div>
  );
}
