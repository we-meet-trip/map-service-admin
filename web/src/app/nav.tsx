import type { ReactNode } from 'react';
import {
  IconAudit,
  IconCloud,
  IconDashboard,
  IconDatabase,
  IconJobs,
  IconMonitor,
  IconPin,
  IconPlug,
  IconUsers,
} from '../components/Icons';

export interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Match only the exact path (used for the index route). */
  end?: boolean;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    to: '/',
    label: '개요',
    icon: <IconDashboard />,
    end: true,
    description: '서비스 헬스 · 핵심 지표 롤업',
  },
  {
    to: '/external',
    label: '외부 API',
    icon: <IconPlug />,
    description: '외부 제공자 상태 · 수동 프로브',
  },
  {
    to: '/weather',
    label: '기상 수집',
    icon: <IconCloud />,
    description: 'KMA 폴링 · 격자 · 강제 수집',
  },
  {
    to: '/places',
    label: '장소 · 금지구역',
    icon: <IconPin />,
    description: '장소 통계 · 비행 금지구역 관리',
  },
  {
    to: '/users',
    label: '사용자',
    icon: <IconUsers />,
    description: '사용자 조회 (열람 감사 기록)',
  },
  {
    to: '/jobs',
    label: '작업 · DLQ',
    icon: <IconJobs />,
    description: '스케줄 작업 · 실패 큐 재처리',
  },
  {
    to: '/db',
    label: '데이터 탐색',
    icon: <IconDatabase />,
    description: 'hub_data 스키마 · 행 조회 · CSV',
  },
  {
    to: '/audit',
    label: '감사 로그',
    icon: <IconAudit />,
    description: '운영자 액션 감사 추적',
  },
  {
    to: '/monitoring',
    label: '모니터링',
    icon: <IconMonitor />,
    description: '외부 대시보드 패널',
  },
];
