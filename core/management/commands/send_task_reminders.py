from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.apps import apps
from core.models import Task
import logging

logger = logging.getLogger(__name__)

# Ленивая инициализация: notification_service будет получен при первом вызове handle().
# Вынесен на уровень модуля, чтобы тесты могли мокировать его по пути
# core.management.commands.send_task_reminders.notification_service
notification_service = None


def _get_notification_service():
    """
    Возвращает сервис уведомлений из конфигурации приложения.
    Используется ленивая инициализация, чтобы избежать проблем
    при импорте до готовности Django.
    """
    return apps.get_app_config('core').notification_service


class Command(BaseCommand):
    help = 'Отправляет напоминания о задачах, срок которых наступит через час'

    def handle(self, *args, **options):
        # Получаем сервис уведомлений (или используем уже установленный мок в тестах)
        global notification_service
        if notification_service is None:
            notification_service = _get_notification_service()

        now = timezone.now()
        one_hour_later = now + timedelta(hours=1)

        tasks = Task.objects.filter(
            completed=False,
            due_date__gte=now,
            due_date__lte=one_hour_later,
            reminder_sent=False
        ).select_related('user', 'client')

        count = 0
        for task in tasks:
            try:
                result = notification_service.notify_task_reminder(task)

                # Считаем успехом, если хотя бы один канал не вернул None
                if any(v for v in result.values() if v is not None):
                    task.reminder_sent = True
                    task.save(update_fields=['reminder_sent'])
                    count += 1
                    logger.info(f"Reminder sent for task {task.id}")

            except Exception as e:
                logger.error(f"Failed to send reminders for task {task.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f'Successfully sent {count} reminders')
        )