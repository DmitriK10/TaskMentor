from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Task
from core.services.notification_service import send_task_reminder_notification
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет напоминания о задачах, срок которых наступит через час'

    def handle(self, *args, **options):
        now = timezone.now()
        one_hour_later = now + timedelta(hours=1)

        # Ищем невыполненные задачи, срок между now и one_hour_later, у которых ещё не отправлено напоминание
        tasks = Task.objects.filter(
            completed=False,
            due_date__gte=now,
            due_date__lte=one_hour_later,
            reminder_sent=False
        ).select_related('user', 'client')

        count = 0
        for task in tasks:
            try:
                # send_task_reminder_notification возвращает True, если письмо отправлено
                success = send_task_reminder_notification(task)
                if success:
                    task.reminder_sent = True
                    task.save(update_fields=['reminder_sent'])
                    count += 1
                    logger.info(f"Reminder sent for task {task.id}")
                else:
                    logger.info(f"Reminder not sent for task {task.id} (user disabled or overdue)")
            except Exception as e:
                logger.error(f"Failed to send reminder for task {task.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f'Successfully sent {count} reminders'))