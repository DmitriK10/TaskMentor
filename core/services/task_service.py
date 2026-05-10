"""
Сервис для управления задачами.
Инкапсулирует бизнес-логику создания, обновления и удаления задач.
"""
import logging
from typing import Optional
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.apps import apps

from core.models import Task, Client, Goal
from core.services.calendar_service import CalendarService
from core.services.google_oauth import GoogleOAuthService

User = get_user_model()
logger = logging.getLogger(__name__)


class TaskService:
    """
    Сервис для работы с задачами. Единая точка входа для всех операций с задачами.
    Следует SRP: отвечает только за задачи.
    """

    def __init__(self, user: User, notification_service=None):
        if not user or not user.is_authenticated:
            raise ValueError("TaskService requires an authenticated user")
        self.user = user
        if notification_service is None:
            notification_service = apps.get_app_config('core').notification_service
        self.notification_service = notification_service

    def create_task(self, data: dict) -> Task:
        """
        Создаёт задачу, отправляет уведомления и синхронизирует с календарём.
        data: dict с полями: client_id, goal_id (опционально), title, description, due_date, priority
        """
        client = Client.objects.get(pk=data['client_id'], user=self.user)
        goal = None
        if data.get('goal_id'):
            goal = Goal.objects.get(pk=data['goal_id'], client__user=self.user)

        task = Task.objects.create(
            user=self.user,
            client=client,
            goal=goal,
            title=data['title'],
            description=data.get('description', ''),
            due_date=data['due_date'],
            priority=data.get('priority', 'medium'),
        )

        # Отправка уведомлений (только для будущих задач)
        if task.due_date > timezone.now():
            self.notification_service.notify_task_created(task)

        # Синхронизация с Google Calendar
        self._sync_calendar(task, create=True)

        return task

    def update_task(self, task: Task, data: dict) -> Task:
        """
        Обновляет задачу, синхронизирует с календарём.
        """
        # Обновляем поля
        if 'client_id' in data:
            task.client = Client.objects.get(pk=data['client_id'], user=self.user)
        if 'goal_id' in data:
            if data['goal_id']:
                task.goal = Goal.objects.get(pk=data['goal_id'], client__user=self.user)
            else:
                task.goal = None
        if 'title' in data:
            task.title = data['title']
        if 'description' in data:
            task.description = data['description']
        if 'due_date' in data:
            task.due_date = data['due_date']
        if 'priority' in data:
            task.priority = data['priority']

        task.save()

        # Синхронизация с календарём
        self._sync_calendar(task, create=False)

        return task

    def delete_task(self, task: Task) -> None:
        """Удаляет задачу и связанное событие в календаре."""
        self._sync_calendar(task, delete=True)
        task.delete()

    def toggle_complete(self, task: Task) -> Task:
        """Переключает статус выполнения задачи."""
        task.completed = not task.completed
        task.save()
        return task

    def _sync_calendar(self, task: Task, create: bool = False, delete: bool = False) -> None:
        """Внутренний метод для синхронизации с Google Calendar."""
        if not GoogleOAuthService.is_connected(self.user):
            return

        calendar = CalendarService(self.user)
        if not calendar.is_available:
            return

        try:
            if create:
                calendar.create_event(task)
            elif delete:
                calendar.delete_event(task)
            else:
                calendar.update_event(task)
        except Exception as e:
            logger.error(f'Google Calendar sync failed for task {task.id}: {e}')