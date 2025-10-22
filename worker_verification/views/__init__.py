from .worker_views import WorkerViewSet
from .document_views import DocumentViewSet
from .client_views import ClientViewSet
from .dashboard_views import (
    DashboardStatsView,
    DashboardWeeklyTrendsView,
    DashboardMonthlyTrendsView
)

__all__ = [
    'WorkerViewSet',
    'DocumentViewSet',
    'ClientViewSet',
    'DashboardStatsView',
    'DashboardWeeklyTrendsView',
    'DashboardMonthlyTrendsView',
]