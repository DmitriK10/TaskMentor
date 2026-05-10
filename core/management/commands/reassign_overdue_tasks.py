from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
from django.conf import settings
from core.models import Task
import logging

logger = logging.getLogger(__name__)

# Час дня (UTC), на который переносятся просроченные задачи.
# Вынесен в настройки через TASK_DEFAULT_HOUR (по умолчанию 10).
DEFAULT_TASK_HOUR = 10


class Command(BaseCommand):
    help = 'Переносит просроченные невыполненные задачи на ближайшие свободные дни'

    def handle(self, *args, **options):
        now = timezone.now()
        task_hour = getattr(settings, 'TASK_DEFAULT_HOUR', DEFAULT_TASK_HOUR)

        # Находим все невыполненные задачи с истекшим сроком
        overdue_tasks = Task.objects.filter(
            completed=False,
            due_date__lt=now
        ).select_related('user').order_by('priority')

        count = 0

        # Группируем по пользователям для независимой обработки
        users_tasks = {}
        for task in overdue_tasks:
            users_tasks.setdefault(task.user, []).append(task)

        for user, tasks in users_tasks.items():
            # Сортируем задачи по приоритету: high → medium → low
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            tasks.sort(key=lambda t: priority_order.get(t.priority, 2))

            current_date = now.date()

            # Словарь: дата -> количество задач, уже запланированных на этот день
            daily_counts = {}

            # Загружаем существующие невыполненные будущие задачи пользователя
            existing_tasks = Task.objects.filter(
                user=user,
                completed=False,
                due_date__gte=now
            ).values('due_date__date')

            for et in existing_tasks:
                date = et['due_date__date']
                daily_counts[date] = daily_counts.get(date, 0) + 1

            max_per_day = getattr(settings, 'MAX_TASKS_PER_DAY', 5)

            for task in tasks:
                target_date = current_date

                # Ищем первый день, на который можно перенести задачу
                while True:
                    if daily_counts.get(target_date, 0) < max_per_day:
                        # Устанавливаем время на task_hour:00 UTC
                        naive_dt = datetime.combine(
                            target_date,
                            datetime.min.time()
                        ) + timedelta(hours=task_hour)
                        new_due = timezone.make_aware(naive_dt)

                        task.due_date = new_due
                        task.save(update_fields=['due_date'])

                        daily_counts[target_date] = daily_counts.get(target_date, 0) + 1
                        count += 1

                        self.stdout.write(
                            f'Task {task.id} "{task.title}" reassigned to {new_due}'
                        )
                        break

                    target_date += timedelta(days=1)

        self.stdout.write(
            self.style.SUCCESS(f'Successfully reassigned {count} overdue tasks')
        )