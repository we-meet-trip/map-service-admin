import { createBrowserRouter } from 'react-router-dom';
import { RootLayout } from './RootLayout';
import { RequireAuth } from './RequireAuth';
import { LoginPage } from '../pages/LoginPage';
import { OverviewPage } from '../pages/OverviewPage';
import { ExternalPage } from '../pages/ExternalPage';
import { WeatherPage } from '../pages/WeatherPage';
import { PlacesPage } from '../pages/PlacesPage';
import { UsersPage } from '../pages/UsersPage';
import { JobsPage } from '../pages/JobsPage';
import { DbPage } from '../pages/DbPage';
import { AuditPage } from '../pages/AuditPage';
import { MonitoringPage } from '../pages/MonitoringPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { OperatorsPage } from '../pages/OperatorsPage';
import { ModerationPage } from '../pages/ModerationPage';

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <OverviewPage /> },
          { path: 'external', element: <ExternalPage /> },
          { path: 'weather', element: <WeatherPage /> },
          { path: 'places', element: <PlacesPage /> },
          { path: 'users', element: <UsersPage /> },
          { path: 'jobs', element: <JobsPage /> },
          { path: 'db', element: <DbPage /> },
          { path: 'audit', element: <AuditPage /> },
          { path: 'monitoring', element: <MonitoringPage /> },
          { path: 'operators', element: <OperatorsPage /> },
          { path: 'moderation', element: <ModerationPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
