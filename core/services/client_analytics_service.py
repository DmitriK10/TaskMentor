"""
Сервис для агрегации аналитики по клиенту.
Следует SRP: отвечает только за расчет метрик клиента.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Avg, QuerySet

from ..models import Client, Task, MoodEntry, Goal


@dataclass
class TaskStatistics:
    """DTO для статистики задач."""
    total: int
    completed: int
    percent: int
    upcoming: List[Any]  # список предстоящих задач (DTO или объекты)


@dataclass
class MoodAnalytics:
    """DTO для аналитики настроения."""
    entries: List[MoodEntry]
    data: List[Dict[str, Any]]
    average: Optional[float]


@dataclass
class UpcomingTask:
    """DTO для предстоящей задачи."""
    id: int
    title: str
    due_date: date
    priority: str
    priority_display: str


@dataclass
class FullAnalytics:
    """DTO для полной аналитики клиента."""
    task_stats: TaskStatistics
    mood_analytics: MoodAnalytics
    goals: List[Dict[str, Any]]


class ClientAnalyticsService:
    """
    Сервис для расчета аналитики клиента.

    Ответственности:
    - Расчет статистики задач
    - Анализ настроения за период
    - Получение предстоящих задач
    """

    def __init__(self, client: Client):
        self._client = client

    def get_task_statistics(self) -> TaskStatistics:
        """Рассчитывает статистику выполнения задач клиента."""
        tasks: QuerySet[Task] = self._client.tasks.all()
        total = tasks.count()
        completed = tasks.filter(completed=True).count()
        percent = int(completed / total * 100) if total > 0 else 0
        upcoming = self.get_upcoming_tasks(limit=5)

        return TaskStatistics(
            total=total,
            completed=completed,
            percent=percent,
            upcoming=upcoming
        )

    def get_upcoming_tasks(self, limit: int = 5) -> List[UpcomingTask]:
        """Возвращает список предстоящих невыполненных задач."""
        today = timezone.now().date()
        tasks = self._client.tasks.filter(
            completed=False,
            due_date__date__gte=today
        ).order_by('due_date')[:limit]

        return [
            UpcomingTask(
                id=task.id,
                title=task.title,
                due_date=task.due_date.date(),
                priority=task.priority,
                priority_display=task.get_priority_display()
            )
            for task in tasks
        ]

    def get_mood_analytics(self, days: int = 30) -> MoodAnalytics:
        """Анализирует настроение клиента за указанный период."""
        cutoff_date = timezone.now().date() - timedelta(days=days)

        entries_queryset: QuerySet[MoodEntry] = MoodEntry.objects.filter(
            client=self._client,
            date__gte=cutoff_date
        ).order_by('-date')

        # Данные для графика (в хронологическом порядке)
        entries_for_chart = entries_queryset.order_by('date')
        chart_data = [
            {
                'date': entry.date.strftime('%d.%m.%Y'),
                'mood_score': entry.mood_score
            }
            for entry in entries_for_chart
        ]

        # Среднее значение
        avg_result = entries_queryset.aggregate(avg=Avg('mood_score'))
        average = avg_result['avg']

        return MoodAnalytics(
            entries=list(entries_queryset[:days]),
            data=chart_data,
            average=float(average) if average is not None else None
        )

    def get_goals_with_progress(self) -> List[Dict[str, Any]]:
        """Возвращает цели клиента с прогрессом выполнения.
        Оптимизировано: использует prefetch_related для избежания N+1 запросов.
        """
        goals: QuerySet[Goal] = self._client.goals.prefetch_related('tasks')
        result = []

        for goal in goals:
            tasks = goal.tasks.all()   # уже загружены в кэш
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if t.completed)
            progress = int(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

            result.append({
                'goal': goal,
                'progress_percent': progress,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks
            })

        return result

    def get_full_analytics(self, mood_days: int = 30) -> FullAnalytics:
        """Возвращает полную аналитику клиента одним вызовом."""
        task_stats = self.get_task_statistics()
        mood_analytics = self.get_mood_analytics(days=mood_days)
        goals = self.get_goals_with_progress()

        return FullAnalytics(
            task_stats=task_stats,
            mood_analytics=mood_analytics,
            goals=goals
        )


class ClientAnalyticsFacade:
    """
    Фасад для получения полной аналитики клиента в виде словаря для шаблона.
    """

    def __init__(self, client: Client):
        self._service = ClientAnalyticsService(client)

    def get_full_context(self) -> Dict[str, Any]:
        """Возвращает полный контекст для страницы деталей клиента."""
        analytics = self._service.get_full_analytics(mood_days=30)

        return {
            # Статистика задач
            'total_tasks': analytics.task_stats.total,
            'completed_tasks': analytics.task_stats.completed,
            'task_progress_percent': analytics.task_stats.percent,
            'upcoming_tasks': analytics.task_stats.upcoming,

            # Настроение
            'mood_entries': analytics.mood_analytics.entries,
            'mood_data': analytics.mood_analytics.data,
            'average_mood': analytics.mood_analytics.average,

            # Цели
            'goals': analytics.goals,
        }