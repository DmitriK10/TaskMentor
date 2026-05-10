# core/tests/test_services.py
"""
Тесты для сервисов приложения.
"""
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core import mail
from unittest.mock import patch, MagicMock
from core.models import Client, Task, NotificationSettings, PushSubscription, GoogleToken
from core.services.base import notification_service, NotificationPayload
from core.services.calendar_service import CalendarService
from core.services.google_oauth import GoogleOAuthService
from core.services.task_service import TaskService
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class NotificationServiceTests(TestCase):
    """Тесты сервиса уведомлений."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='12345'
        )
        self.client_obj = Client.objects.create(
            user=self.user,
            name='Test Client'
        )
        self.task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Test Task',
            due_date=timezone.now() + timedelta(days=1)
        )
        # Убеждаемся, что настройки уведомлений существуют
        NotificationSettings.objects.get_or_create(user=self.user, defaults={'receive_emails': True})
        # Используем глобальный сервис уведомлений (уже сконфигурирован с каналами)
        self.service = notification_service

    @override_settings(DEFAULT_FROM_EMAIL='test@test.com')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_notify_task_created_sends_email(self):
        """Проверяет отправку email при создании задачи."""
        self.user.notification_settings.receive_emails = True
        self.user.notification_settings.save()

        result = self.service.notify_task_created(self.task)

        # Проверяем, что email был отправлен
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Test Task', mail.outbox[0].subject)
        # Также проверяем, что результат содержит успешную отправку по EmailChannel
        self.assertEqual(result.get('EmailChannel'), 'sent')

    def test_notify_respects_user_settings(self):
        """Проверяет, что уведомления учитывают настройки пользователя."""
        self.user.notification_settings.receive_emails = False
        self.user.notification_settings.save()

        with patch('core.services.base.EmailChannel.send') as mock_send:
            payload = NotificationPayload(
                title='Test',
                body='Test body',
                user=self.user
            )
            self.service.notify(payload)
            mock_send.assert_not_called()

    def test_payload_formatting(self):
        """Проверяет форматирование сообщения и возврат результатов по каналам."""
        self.user.notification_settings.receive_emails = True
        self.user.notification_settings.save()

        result = self.service.notify_task_created(self.task)

        # Результат должен содержать ключи каналов (EmailChannel, PushChannel)
        self.assertIn('EmailChannel', result)
        self.assertIn('PushChannel', result)


class CalendarServiceTests(TestCase):
    """Тесты сервиса календаря."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='calendaruser',
            email='cal@example.com',
            password='12345'
        )
        self.client_obj = Client.objects.create(
            user=self.user,
            name='Calendar Client'
        )
        self.task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Calendar Task',
            due_date=timezone.now() + timedelta(days=1)
        )

    def test_service_unavailable_without_token(self):
        """Проверяет, что сервис недоступен без токена."""
        service = CalendarService(self.user)
        self.assertFalse(service.is_available)

    def test_service_available_with_token(self):
        """Проверяет доступность сервиса с токеном."""
        GoogleToken.objects.create(
            user=self.user,
            access_token='test_token',
            refresh_token='test_refresh',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        service = CalendarService(self.user)
        self.assertTrue(service.is_available)

    @patch('core.services.calendar_service.build')
    def test_create_event(self, mock_build):
        """Проверяет создание события в календаре."""
        GoogleToken.objects.create(
            user=self.user,
            access_token='test_token',
            refresh_token='test_refresh',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            'id': 'event_123'
        }

        service = CalendarService(self.user)
        event_id = service.create_event(self.task)

        self.assertEqual(event_id, 'event_123')
        self.task.refresh_from_db()
        self.assertEqual(self.task.google_event_id, 'event_123')


class GoogleOAuthServiceTests(TestCase):
    """Тесты OAuth сервиса."""

    def test_is_connected_without_token(self):
        user = User.objects.create_user(
            username='oauthuser',
            email='oauth@example.com',
            password='12345'
        )
        self.assertFalse(GoogleOAuthService.is_connected(user))

    def test_is_connected_with_token(self):
        user = User.objects.create_user(
            username='oauthuser2',
            email='oauth2@example.com',
            password='12345'
        )
        GoogleToken.objects.create(
            user=user,
            access_token='test',
            refresh_token='test',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        self.assertTrue(GoogleOAuthService.is_connected(user))

    def test_revoke_access(self):
        user = User.objects.create_user(
            username='oauthuser3',
            email='oauth3@example.com',
            password='12345'
        )
        GoogleToken.objects.create(
            user=user,
            access_token='test',
            refresh_token='test',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        GoogleOAuthService.revoke_access(user)
        # Обновляем объект пользователя из базы, чтобы атрибут google_token исчез
        user.refresh_from_db()
        self.assertFalse(GoogleOAuthService.is_connected(user))


class TaskServiceTests(TestCase):
    """Тесты сервиса задач."""

    def setUp(self):
        self.user = User.objects.create_user(username='taskuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Test Client')
        # Убедимся, что настройки уведомлений есть
        NotificationSettings.objects.get_or_create(user=self.user, defaults={'receive_emails': True})

    def test_create_task_sets_user(self):
        service = TaskService(self.user)
        due = timezone.now() + timedelta(days=1)
        task = service.create_task({
            'client_id': self.client_obj.id,
            'title': 'Test Task',
            'due_date': due,
        })
        self.assertEqual(task.user, self.user)
        self.assertEqual(task.title, 'Test Task')

    @patch('core.services.task_service.notification_service.notify_task_created')
    def test_create_task_sends_notification(self, mock_notify):
        service = TaskService(self.user)
        due = timezone.now() + timedelta(days=1)
        service.create_task({
            'client_id': self.client_obj.id,
            'title': 'Task',
            'due_date': due,
        })
        mock_notify.assert_called_once()

    def test_update_task(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Old',
            due_date=timezone.now()
        )
        service = TaskService(self.user)
        new_due = timezone.now() + timedelta(days=5)
        service.update_task(task, {'title': 'Updated', 'due_date': new_due})
        self.assertEqual(task.title, 'Updated')
        self.assertEqual(task.due_date, new_due)

    def test_delete_task(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='To delete',
            due_date=timezone.now()
        )
        service = TaskService(self.user)
        service.delete_task(task)
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_toggle_complete(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Toggle me',
            due_date=timezone.now(),
            completed=False
        )
        service = TaskService(self.user)
        service.toggle_complete(task)
        self.assertTrue(task.completed)
        service.toggle_complete(task)
        self.assertFalse(task.completed)