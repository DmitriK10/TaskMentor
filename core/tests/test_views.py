# core/tests/test_views.py
from django.test import TestCase, Client as TestClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
from django.core import mail
from django.test import override_settings
from django.core.management import call_command
from io import StringIO
from unittest.mock import patch, MagicMock
from django.conf import settings
from pywebpush import WebPushException

from core.models import Client, Task, MoodEntry, Goal, NotificationSettings, PushSubscription

User = get_user_model()


class MoodEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345', email='testuser@example.com')
        self.client_user = TestClient()
        self.client_user.login(username='testuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Иван Петров')

    def test_add_mood_entry(self):
        response = self.client_user.post(
            reverse('core:mood_add', args=[self.client_obj.pk]),
            {
                'date': date.today().isoformat(),
                'mood_score': 8,
                'notes': 'Хорошее настроение'
            }
        )
        self.assertRedirects(response, reverse('core:client_detail', args=[self.client_obj.pk]))
        self.assertTrue(MoodEntry.objects.filter(client=self.client_obj, date=date.today()).exists())

    def test_mood_entry_protected(self):
        self.client_user.logout()
        response = self.client_user.post(
            reverse('core:mood_add', args=[self.client_obj.pk]),
            {'date': date.today().isoformat(), 'mood_score': 5}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class ClientDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345', email='testuser@example.com')
        self.client_user = TestClient()
        self.client_user.login(username='testuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Иван Петров')

        Task.objects.create(user=self.user, client=self.client_obj, title='Задача 1',
                            due_date=timezone.now() + timedelta(days=1), completed=True)
        Task.objects.create(user=self.user, client=self.client_obj, title='Задача 2',
                            due_date=timezone.now() + timedelta(days=2), completed=False)
        Task.objects.create(user=self.user, client=self.client_obj, title='Задача 3',
                            due_date=timezone.now() - timedelta(days=1), completed=False)

        MoodEntry.objects.create(client=self.client_obj, date=date.today() - timedelta(days=1), mood_score=7)
        MoodEntry.objects.create(client=self.client_obj, date=date.today() - timedelta(days=2), mood_score=6)

    def test_client_detail_view_status(self):
        response = self.client_user.get(reverse('core:client_detail', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иван Петров')

    def test_client_detail_progress(self):
        response = self.client_user.get(reverse('core:client_detail', args=[self.client_obj.pk]))
        self.assertEqual(response.context['total_tasks'], 3)
        self.assertEqual(response.context['completed_tasks'], 1)
        self.assertEqual(response.context['task_progress_percent'], 33)

    def test_client_detail_mood_data(self):
        response = self.client_user.get(reverse('core:client_detail', args=[self.client_obj.pk]))
        mood_data = response.context['mood_data']
        self.assertEqual(len(mood_data), 2)
        expected_date_1 = (date.today() - timedelta(days=2)).strftime('%d.%m.%Y')
        expected_date_2 = (date.today() - timedelta(days=1)).strftime('%d.%m.%Y')
        self.assertEqual(mood_data[0]['date'], expected_date_1)
        self.assertEqual(mood_data[1]['date'], expected_date_2)


class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser2', password='12345', email='testuser2@example.com')
        self.client.login(username='testuser2', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент для теста')
        NotificationSettings.objects.get_or_create(user=self.user, defaults={'receive_emails': True})
        self.assertTrue(self.user.notification_settings.receive_emails)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_task_creation_sends_email(self):
        future_date = timezone.now() + timedelta(days=1)
        response = self.client.post(reverse('core:task_create'), {
            'client': self.client_obj.pk,
            'title': 'Тестовая задача',
            'description': 'Описание',
            'due_date': future_date.strftime('%Y-%m-%d %H:%M:%S'),
            'priority': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Тестовая задача', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to[0], self.user.email)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_task_creation_no_email_for_past_date(self):
        past_date = timezone.now() - timedelta(days=1)
        response = self.client.post(reverse('core:task_create'), {
            'client': self.client_obj.pk,
            'title': 'Просроченная задача',
            'description': 'Описание',
            'due_date': past_date.strftime('%Y-%m-%d %H:%M:%S'),
            'priority': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_task_creation_respects_user_settings(self):
        notif_settings = self.user.notification_settings
        notif_settings.receive_emails = False
        notif_settings.save()

        future_date = timezone.now() + timedelta(days=1)
        response = self.client.post(reverse('core:task_create'), {
            'client': self.client_obj.pk,
            'title': 'Задача без уведомления',
            'description': 'Описание',
            'due_date': future_date.strftime('%Y-%m-%d %H:%M:%S'),
            'priority': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)


class GoalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='goaluser', password='12345', email='goaluser@example.com')
        self.client_user = TestClient()
        self.client_user.login(username='goaluser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент с целями')

    def test_goal_creation(self):
        goal = Goal.objects.create(
            client=self.client_obj,
            title='Тестовая цель',
            description='Описание цели',
            target_date=date.today() + timedelta(days=30)
        )
        self.assertEqual(goal.title, 'Тестовая цель')
        self.assertEqual(goal.client, self.client_obj)
        self.assertEqual(goal.target_date, date.today() + timedelta(days=30))

    def test_goal_create_view(self):
        response = self.client_user.post(
            reverse('core:goal_create', args=[self.client_obj.pk]),
            {
                'title': 'Новая цель',
                'description': 'Описание',
                'target_date': (date.today() + timedelta(days=10)).isoformat()
            }
        )
        self.assertRedirects(response, reverse('core:client_detail', args=[self.client_obj.pk]))
        self.assertTrue(Goal.objects.filter(title='Новая цель', client=self.client_obj).exists())

    def test_goal_update_view(self):
        goal = Goal.objects.create(client=self.client_obj, title='Старая цель')
        response = self.client_user.post(
            reverse('core:goal_update', args=[goal.pk]),
            {
                'title': 'Обновлённая цель',
                'description': 'Новое описание',
                'target_date': (date.today() + timedelta(days=20)).isoformat()
            }
        )
        self.assertRedirects(response, reverse('core:client_detail', args=[self.client_obj.pk]))
        goal.refresh_from_db()
        self.assertEqual(goal.title, 'Обновлённая цель')
        self.assertEqual(goal.description, 'Новое описание')
        self.assertEqual(goal.target_date, date.today() + timedelta(days=20))

    def test_goal_delete_view(self):
        goal = Goal.objects.create(client=self.client_obj, title='Цель для удаления')
        response = self.client_user.post(reverse('core:goal_delete', args=[goal.pk]))
        self.assertRedirects(response, reverse('core:client_detail', args=[self.client_obj.pk]))
        self.assertFalse(Goal.objects.filter(pk=goal.pk).exists())

    def test_goal_progress_calculation(self):
        goal = Goal.objects.create(client=self.client_obj, title='Цель с задачами')
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            goal=goal,
            title='Задача 1',
            due_date=timezone.now() + timedelta(days=1),
            completed=True
        )
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            goal=goal,
            title='Задача 2',
            due_date=timezone.now() + timedelta(days=2),
            completed=False
        )
        response = self.client_user.get(reverse('core:client_detail', args=[self.client_obj.pk]))
        goals_in_context = response.context['goals']
        self.assertEqual(len(goals_in_context), 1)
        self.assertEqual(goals_in_context[0]['progress_percent'], 50)

    def test_goal_access_control(self):
        other_user = User.objects.create_user(username='other', password='12345', email='other@example.com')
        other_client = Client.objects.create(user=other_user, name='Чужой клиент')
        other_goal = Goal.objects.create(client=other_client, title='Чужая цель')

        response = self.client_user.get(reverse('core:goal_update', args=[other_goal.pk]))
        self.assertEqual(response.status_code, 404)

        response = self.client_user.post(reverse('core:goal_delete', args=[other_goal.pk]))
        self.assertEqual(response.status_code, 404)

        self.assertTrue(Goal.objects.filter(pk=other_goal.pk).exists())


class ReminderCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reminderuser', password='12345', email='reminder@example.com')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент для напоминаний')
        NotificationSettings.objects.get_or_create(user=self.user, defaults={'receive_emails': True})
        self.user.notification_settings.receive_emails = True
        self.user.notification_settings.save()

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reminder_sent_for_task_due_in_one_hour(self):
        due = timezone.now() + timedelta(minutes=59)
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Тестовая задача',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        self.assertIn('Successfully sent 1 reminders', out.getvalue())
        task.refresh_from_db()
        self.assertTrue(task.reminder_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Напоминание', mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reminder_not_sent_if_already_sent(self):
        due = timezone.now() + timedelta(minutes=59)
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Тест',
            due_date=due,
            completed=False,
            reminder_sent=True
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        self.assertIn('Successfully sent 0 reminders', out.getvalue())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reminder_not_sent_if_user_disabled(self):
        self.user.notification_settings.receive_emails = False
        self.user.notification_settings.save()
        due = timezone.now() + timedelta(minutes=59)
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Тест',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        self.assertIn('Successfully sent 0 reminders', out.getvalue())
        self.assertEqual(len(mail.outbox), 0)
        task.refresh_from_db()
        self.assertFalse(task.reminder_sent)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reminder_not_sent_for_past_task(self):
        due = timezone.now() - timedelta(minutes=30)
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Просроченная',
            due_date=due,
            completed=False,
            reminder_sent=False
        )
        out = StringIO()
        call_command('send_task_reminders', stdout=out)
        self.assertIn('Successfully sent 0 reminders', out.getvalue())
        self.assertEqual(len(mail.outbox), 0)


class ClientModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='clientuser', password='12345')
        self.client_obj = Client.objects.create(
            user=self.user,
            name='Тестовый клиент',
            email='test@example.com',
            phone='1234567890'
        )

    def test_client_str(self):
        self.assertEqual(str(self.client_obj), 'Тестовый клиент')

    def test_get_task_stats_no_tasks(self):
        stats = self.client_obj.get_task_stats()
        self.assertEqual(stats, {'total': 0, 'completed': 0, 'percent': 0})

    def test_get_task_stats_with_tasks(self):
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Задача 1',
            due_date=timezone.now(),
            completed=True
        )
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Задача 2',
            due_date=timezone.now(),
            completed=False
        )
        stats = self.client_obj.get_task_stats()
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['completed'], 1)
        self.assertEqual(stats['percent'], 50)

    def test_get_upcoming_tasks(self):
        future = timezone.now() + timedelta(days=1)
        past = timezone.now() - timedelta(days=1)
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Будущая задача',
            due_date=future,
            completed=False
        )
        Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Просроченная задача',
            due_date=past,
            completed=False
        )
        upcoming = self.client_obj.get_upcoming_tasks(limit=5)
        self.assertEqual(upcoming.count(), 1)
        self.assertEqual(upcoming[0].title, 'Будущая задача')


class TaskModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='taskuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')

    def test_task_str(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Тестовая задача',
            due_date=timezone.now()
        )
        self.assertEqual(str(task), 'Тестовая задача')

    def test_reminder_sent_default_false(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Задача',
            due_date=timezone.now()
        )
        self.assertFalse(task.reminder_sent)


class ClientCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='createuser', password='12345')
        self.client.login(username='createuser', password='12345')

    def test_create_client_get(self):
        response = self.client.get(reverse('core:client_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/client_form.html')

    def test_create_client_post(self):
        response = self.client.post(reverse('core:client_create'), {
            'name': 'Новый клиент',
            'email': 'new@example.com',
            'phone': '1234567890',
            'birth_date': '2000-01-01',
            'notes': 'Тестовые заметки'
        })
        self.assertRedirects(response, reverse('core:client_list'))
        self.assertTrue(Client.objects.filter(name='Новый клиент').exists())
        new_client = Client.objects.get(name='Новый клиент')
        self.assertEqual(new_client.user, self.user)


class ClientUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='updateuser', password='12345')
        self.client.login(username='updateuser', password='12345')
        self.client_obj = Client.objects.create(
            user=self.user,
            name='Старое имя'
        )

    def test_update_client_get(self):
        response = self.client.get(reverse('core:client_update', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Старое имя')

    def test_update_client_post(self):
        response = self.client.post(reverse('core:client_update', args=[self.client_obj.pk]), {
            'name': 'Новое имя',
            'email': '',
            'phone': '',
            'birth_date': '',
            'notes': ''
        })
        self.assertRedirects(response, reverse('core:client_list'))
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.name, 'Новое имя')

    def test_cannot_update_other_users_client(self):
        other_user = User.objects.create_user(username='other', password='12345')
        other_client = Client.objects.create(user=other_user, name='Чужой клиент')
        response = self.client.get(reverse('core:client_update', args=[other_client.pk]))
        self.assertEqual(response.status_code, 404)


class ClientDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='deleteuser', password='12345')
        self.client.login(username='deleteuser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Удаляемый клиент')

    def test_delete_client_get(self):
        response = self.client.get(reverse('core:client_delete', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/client_confirm_delete.html')

    def test_delete_client_post(self):
        response = self.client.post(reverse('core:client_delete', args=[self.client_obj.pk]))
        self.assertRedirects(response, reverse('core:client_list'))
        self.assertFalse(Client.objects.filter(pk=self.client_obj.pk).exists())

    def test_cannot_delete_other_users_client(self):
        other_user = User.objects.create_user(username='other', password='12345')
        other_client = Client.objects.create(user=other_user, name='Чужой клиент')
        response = self.client.post(reverse('core:client_delete', args=[other_client.pk]))
        self.assertEqual(response.status_code, 404)


class TaskCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='taskcreator', password='12345')
        self.client.login(username='taskcreator', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент для задачи')
        NotificationSettings.objects.get_or_create(user=self.user)

    def test_create_task_get(self):
        response = self.client.get(reverse('core:task_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/task_form.html')

    def test_create_task_post(self):
        future_date = timezone.now() + timedelta(days=1)
        response = self.client.post(reverse('core:task_create'), {
            'client': self.client_obj.pk,
            'title': 'Новая задача',
            'description': 'Описание',
            'due_date': future_date.strftime('%Y-%m-%dT%H:%M'),
            'priority': 'high'
        })
        self.assertRedirects(response, reverse('core:task_list'))
        self.assertTrue(Task.objects.filter(title='Новая задача').exists())
        task = Task.objects.get(title='Новая задача')
        self.assertEqual(task.user, self.user)
        self.assertEqual(task.client, self.client_obj)
        self.assertFalse(task.completed)
        self.assertFalse(task.reminder_sent)


class TaskUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='taskupdater', password='12345')
        self.client.login(username='taskupdater', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')
        self.task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Старая задача',
            due_date=timezone.now()
        )

    def test_update_task_get(self):
        response = self.client.get(reverse('core:task_update', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Старая задача')

    def test_update_task_post(self):
        future_date = timezone.now() + timedelta(days=2)
        response = self.client.post(reverse('core:task_update', args=[self.task.pk]), {
            'client': self.client_obj.pk,
            'title': 'Обновлённая задача',
            'description': 'Новое описание',
            'due_date': future_date.strftime('%Y-%m-%dT%H:%M'),
            'priority': 'medium'
        })
        self.assertRedirects(response, reverse('core:task_list'))
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, 'Обновлённая задача')

    def test_cannot_update_other_users_task(self):
        other_user = User.objects.create_user(username='other', password='12345')
        other_client = Client.objects.create(user=other_user, name='Чужой клиент')
        other_task = Task.objects.create(
            user=other_user,
            client=other_client,
            title='Чужая задача',
            due_date=timezone.now()
        )
        response = self.client.get(reverse('core:task_update', args=[other_task.pk]))
        self.assertEqual(response.status_code, 404)


class TaskDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='taskdeleter', password='12345')
        self.client.login(username='taskdeleter', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')
        self.task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Удаляемая задача',
            due_date=timezone.now()
        )

    def test_delete_task_post(self):
        response = self.client.post(reverse('core:task_delete', args=[self.task.pk]))
        self.assertRedirects(response, reverse('core:task_list'))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())


class NotificationSettingsFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='settingsuser', password='12345')
        self.client.login(username='settingsuser', password='12345')
        NotificationSettings.objects.get_or_create(user=self.user)

    def test_form_save(self):
        NotificationSettings.objects.filter(user=self.user).delete()
        response = self.client.post(reverse('core:profile'), {
            'receive_emails': True
        })
        self.assertRedirects(response, reverse('core:profile'))
        notif_settings = NotificationSettings.objects.get(user=self.user)
        self.assertTrue(notif_settings.receive_emails)

        response = self.client.post(reverse('core:profile'), {
            'receive_emails': False
        })
        self.assertRedirects(response, reverse('core:profile'))
        notif_settings.refresh_from_db()
        self.assertFalse(notif_settings.receive_emails)


class CronEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cronuser', password='12345', email='cron@example.com')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')
        NotificationSettings.objects.get_or_create(user=self.user, defaults={'receive_emails': True})
        self.user.notification_settings.receive_emails = True
        self.user.notification_settings.save()
        self.due = timezone.now() + timedelta(minutes=30)
        self.task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Задача для крона',
            due_date=self.due,
            completed=False,
            reminder_sent=False
        )

    @override_settings(CRON_TOKEN='test-token')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_cron_endpoint_with_valid_token_in_header(self):
        response = self.client.post(
            reverse('core:cron_reminders'),
            HTTP_AUTHORIZATION='Bearer test-token'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'message': 'Reminders sent successfully'})
        self.task.refresh_from_db()
        self.assertTrue(self.task.reminder_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Напоминание', mail.outbox[0].subject)

    def test_cron_endpoint_without_token(self):
        response = self.client.post(reverse('core:cron_reminders'))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'error': 'Unauthorized'})

    def test_cron_endpoint_with_invalid_token(self):
        response = self.client.post(
            reverse('core:cron_reminders'),
            HTTP_AUTHORIZATION='Bearer wrong-token'
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(CRON_TOKEN=None)
    def test_cron_endpoint_without_token_setting(self):
        response = self.client.post(reverse('core:cron_reminders'))
        self.assertEqual(response.status_code, 500)
        self.assertIn('Server configuration error', response.json()['error'])

class PushSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pushuser', password='12345', email='push@example.com')
        self.client.login(username='pushuser', password='12345')
        self.url = reverse('core:push_subscribe')
        self.vapid_url = reverse('core:vapid_key')
        self.valid_payload = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/xyz',
            'keys': {
                'p256dh': 'BNRDq...',
                'auth': 'xT3...'
            }
        }

    def test_subscribe_creates_subscription(self):
        response = self.client.post(self.url, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        sub = PushSubscription.objects.first()
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.endpoint, self.valid_payload['endpoint'])

    def test_subscribe_updates_existing(self):
        PushSubscription.objects.create(
            user=self.user,
            endpoint=self.valid_payload['endpoint'],
            p256dh='old_p256dh',
            auth='old_auth'
        )
        response = self.client.post(self.url, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        sub = PushSubscription.objects.get(endpoint=self.valid_payload['endpoint'])
        self.assertEqual(sub.p256dh, self.valid_payload['keys']['p256dh'])
        self.assertEqual(sub.auth, self.valid_payload['keys']['auth'])

    def test_subscribe_requires_auth(self):
        self.client.logout()
        response = self.client.post(self.url, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_subscribe_invalid_data(self):
        invalid_payload = {'endpoint': 'https://...'}
        response = self.client.post(self.url, data=invalid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_vapid_key_returns_key(self):
        with override_settings(VAPID_PUBLIC_KEY='test-public-key'):
            response = self.client.get(self.vapid_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'key': 'test-public-key'})

    @patch('core.services.notification_service.webpush')
    def test_send_push_notification_calls_webpush(self, mock_webpush):
        PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/xyz',
            p256dh='test_p256dh',
            auth='test_auth'
        )
        self.user.notification_settings.receive_push = True
        self.user.notification_settings.save()

        from core.services.notification_service import send_push_notification
        send_push_notification(self.user, 'Test title', 'Test body', {'url': '/'})

        mock_webpush.assert_called_once()

    @patch('core.services.notification_service.webpush')
    def test_send_push_notification_handles_410(self, mock_webpush):
        sub = PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/xyz',
            p256dh='test_p256dh',
            auth='test_auth'
        )
        self.user.notification_settings.receive_push = True
        self.user.notification_settings.save()

        mock_exception = MagicMock()
        mock_exception.response.status_code = 410
        mock_webpush.side_effect = WebPushException('Gone', response=mock_exception.response)

        from core.services.notification_service import send_push_notification
        send_push_notification(self.user, 'Test', 'Test')

        self.assertFalse(PushSubscription.objects.filter(pk=sub.pk).exists())

    @patch('core.services.notification_service.webpush')
    def test_send_push_notification_respects_user_settings(self, mock_webpush):
        PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/xyz',
            p256dh='test_p256dh',
            auth='test_auth'
        )
        self.user.notification_settings.receive_push = False
        self.user.notification_settings.save()

        from core.services.notification_service import send_push_notification
        send_push_notification(self.user, 'Test', 'Test')

        mock_webpush.assert_not_called()


class CalendarDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='calendaruser', password='12345')
        self.client.login(username='calendaruser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')
        self.url = reverse('core:calendar_data')

    def test_calendar_data_returns_events(self):
        task = Task.objects.create(
            user=self.user,
            client=self.client_obj,
            title='Тестовая задача',
            due_date=timezone.now(),
            completed=False
        )
        today = timezone.now().date()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        response = self.client.get(self.url, {'start': start, 'end': end})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        event = data[0]
        self.assertEqual(event['id'], task.id)
        self.assertEqual(event['title'], task.title)
        self.assertEqual(event['backgroundColor'], '#FF8C00')
        self.assertEqual(event['extendedProps']['client'], self.client_obj.name)
        self.assertFalse(event['extendedProps']['completed'])

    def test_calendar_data_requires_auth(self):
        self.client.logout()
        response = self.client.get(self.url, {'start': '2025-01-01', 'end': '2025-01-31'})
        self.assertEqual(response.status_code, 401)

    def test_calendar_data_missing_params(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    def test_calendar_data_filters_by_user(self):
        other_user = User.objects.create_user(username='other', password='12345')
        other_client = Client.objects.create(user=other_user, name='Другой клиент')
        Task.objects.create(
            user=other_user,
            client=other_client,
            title='Чужая задача',
            due_date=timezone.now(),
            completed=False
        )
        today = timezone.now().date()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        response = self.client.get(self.url, {'start': start, 'end': end})
        data = response.json()
        self.assertEqual(len(data), 0)


class MoodAverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='mooduser', password='12345')
        self.client.login(username='mooduser', password='12345')
        self.client_obj = Client.objects.create(user=self.user, name='Клиент')
        self.url = reverse('core:client_detail', args=[self.client_obj.pk])

    def test_average_mood_calculation(self):
        today = date.today()
        MoodEntry.objects.create(client=self.client_obj, date=today - timedelta(days=1), mood_score=5)
        MoodEntry.objects.create(client=self.client_obj, date=today - timedelta(days=2), mood_score=7)
        MoodEntry.objects.create(client=self.client_obj, date=today - timedelta(days=3), mood_score=9)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('average_mood', response.context)
        self.assertEqual(response.context['average_mood'], 7.0)

    def test_average_mood_ignores_old_entries(self):
        old_date = date.today() - timedelta(days=31)
        MoodEntry.objects.create(client=self.client_obj, date=old_date, mood_score=10)
        MoodEntry.objects.create(client=self.client_obj, date=date.today(), mood_score=6)
        response = self.client.get(self.url)
        self.assertEqual(response.context['average_mood'], 6.0)

    def test_average_mood_none_if_no_entries(self):
        response = self.client.get(self.url)
        self.assertIsNone(response.context['average_mood'])