"""
Тесты для management команд приложения core.
"""
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from core.models import Task, Client, User


class SendTaskRemindersCommandTest(TestCase):
    """Тесты для команды send_task_reminders."""

    def setUp(self):
        self.user = User.objects.create_user(username='reminderuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Test Client')

    def test_no_tasks(self):
        """Если нет подходящих задач, команда ничего не отправляет."""
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        self.assertIn('Successfully sent 0 reminders', out.getvalue())

    @patch('core.management.commands.send_task_reminders.notification_service')
    def test_reminder_sent_for_task_in_range(self, mock_notification):
        """Проверяет, что для задачи, срок которой наступает через 30-59 минут, отправляется напоминание."""
        due = timezone.now() + timedelta(minutes=30)
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Test Task',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        mock_notification.notify_task_reminder.return_value = {'PushChannel': 'sent'}

        out = StringIO()
        call_command('send_task_reminders', stdout=out)

        mock_notification.notify_task_reminder.assert_called_once_with(task)
        self.assertTrue(Task.objects.get(pk=task.pk).reminder_sent)
        self.assertIn('Successfully sent 1 reminders', out.getvalue())

    @patch('core.management.commands.send_task_reminders.notification_service')
    def test_reminder_not_sent_if_already_sent(self, mock_notification):
        """Не отправляет повторно, если reminder_sent уже True."""
        due = timezone.now() + timedelta(minutes=30)
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Test Task',
            due_date=due,
            completed=False,
            reminder_sent=True
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        mock_notification.notify_task_reminder.assert_not_called()
        self.assertIn('Successfully sent 0 reminders', out.getvalue())

    @patch('core.management.commands.send_task_reminders.notification_service')
    def test_reminder_not_sent_for_past_task(self, mock_notification):
        """Не отправляет для просроченной задачи."""
        due = timezone.now() - timedelta(minutes=30)
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Past Task',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        mock_notification.notify_task_reminder.assert_not_called()
        self.assertIn('Successfully sent 0 reminders', out.getvalue())

    @patch('core.management.commands.send_task_reminders.notification_service')
    def test_reminder_not_sent_for_far_future_task(self, mock_notification):
        """Не отправляет для задачи, срок которой дальше часа."""
        due = timezone.now() + timedelta(hours=2)
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Future Task',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        mock_notification.notify_task_reminder.assert_not_called()
        self.assertIn('Successfully sent 0 reminders', out.getvalue())


@override_settings(MAX_TASKS_PER_DAY=2)
class ReassignOverdueTasksCommandTest(TestCase):
    """Тесты для команды reassign_overdue_tasks."""

    def setUp(self):
        self.user = User.objects.create_user(username='reassignuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Test Client')
        # Фиксируем текущее время
        self.now = timezone.now()
        # Создаём просроченные задачи с разными приоритетами
        self.task_high = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='High priority overdue',
            due_date=self.now - timedelta(days=1),
            priority='high',
            completed=False
        )
        self.task_medium = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Medium priority overdue',
            due_date=self.now - timedelta(days=2),
            priority='medium',
            completed=False
        )
        self.task_low = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Low priority overdue',
            due_date=self.now - timedelta(days=3),
            priority='low',
            completed=False
        )

    def test_reassign_overdue_tasks_respects_max_per_day(self):
        """Проверяет, что переносится не более MAX_TASKS_PER_DAY задач на один день."""
        # Удаляем все будущие задачи, чтобы слоты были свободны
        Task.objects.filter(user=self.user, due_date__gte=self.now).delete()
        out = StringIO()
        call_command('reassign_overdue_tasks', stdout=out)

        # Проверяем, что на каждый день не более MAX_TASKS_PER_DAY (2)
        tasks_by_date = {}
        for task in [self.task_high, self.task_medium, self.task_low]:
            task.refresh_from_db()
            date = task.due_date.date()
            tasks_by_date[date] = tasks_by_date.get(date, 0) + 1

        for date, count in tasks_by_date.items():
            self.assertLessEqual(count, 2)

        # Все три задачи должны быть перенесены
        self.assertEqual(len(tasks_by_date), 2)  # на два дня (сегодня и завтра)
        self.assertIn('Successfully reassigned 3 overdue tasks', out.getvalue())

    def test_reassign_does_not_affect_future_tasks(self):
        """Проверяет, что будущие задачи не переносятся."""
        future_task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Future task',
            due_date=self.now + timedelta(days=5),
            completed=False
        )
        out = StringIO()
        call_command('reassign_overdue_tasks', stdout=out)
        future_task.refresh_from_db()
        self.assertEqual(future_task.due_date.date(), (self.now + timedelta(days=5)).date())
        # Просроченные задачи должны быть перенесены
        self.task_high.refresh_from_db()
        self.assertNotEqual(self.task_high.due_date.date(), (self.now - timedelta(days=1)).date())

    def test_reassign_prioritizes_high_priority_first(self):
        """Проверяет, что задачи с высоким приоритетом переносятся раньше."""
        # Удаляем все будущие задачи, чтобы слоты на сегодня были свободны
        Task.objects.filter(user=self.user, due_date__gte=self.now).delete()
        out = StringIO()
        call_command('reassign_overdue_tasks', stdout=out)

        today = self.now.date()
        self.task_high.refresh_from_db()
        self.task_medium.refresh_from_db()
        self.task_low.refresh_from_db()

        # high и medium должны занять сегодня (лимит 2), low – завтра
        self.assertEqual(self.task_high.due_date.date(), today)
        self.assertEqual(self.task_medium.due_date.date(), today)
        self.assertEqual(self.task_low.due_date.date(), today + timedelta(days=1))

    def test_no_overdue_tasks(self):
        """Если нет просроченных задач, команда ничего не делает."""
        Task.objects.filter(user=self.user, due_date__lt=self.now).delete()
        out = StringIO()
        call_command('reassign_overdue_tasks', stdout=out)
        self.assertIn('Successfully reassigned 0 overdue tasks', out.getvalue())