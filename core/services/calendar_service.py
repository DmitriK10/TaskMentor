"""
Сервис для работы с Google Calendar API.
Не зависит от OAuth логики (SRP).
"""
import logging
import requests
from typing import Optional
from types import SimpleNamespace
from django.conf import settings
from django.contrib.auth import get_user_model
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from core.models import GoogleToken

User = get_user_model()
logger = logging.getLogger(__name__)


def _requests_request_with_body(method, url, headers=None, body=None):
    """
    Адаптер для библиотеки google-auth, которая передаёт параметр 'body',
    а requests.request ожидает 'data'. Возвращает объект с атрибутом 'data',
    содержащим тело ответа (bytes), что требуется google-auth.
    """
    kwargs = {'method': method, 'url': url, 'headers': headers}
    if body is not None:
        kwargs['data'] = body
    response = requests.request(**kwargs)
    # Оборачиваем response в объект с атрибутом data (bytes)
    return SimpleNamespace(data=response.content, status=response.status_code)


class CalendarService:
    """
    Сервис для управления событиями Google Calendar.
    Использует токены из модели GoogleToken.
    """

    def __init__(self, user: User):
        self.user = user
        self.service = self._build_service()

    def _build_service(self):
        """Создаёт сервис Google Calendar API из сохранённых токенов."""
        try:
            token_obj = GoogleToken.objects.get(user=self.user)
        except GoogleToken.DoesNotExist:
            logger.warning(f"No Google token for user {self.user.id}")
            return None

        # Библиотека google-auth ожидает naive datetime, поэтому убираем timezone
        expiry = token_obj.expires_at
        if expiry and expiry.tzinfo:
            expiry = expiry.replace(tzinfo=None)

        credentials = Credentials(
            token=token_obj.access_token,
            refresh_token=token_obj.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH2_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH2_CLIENT_SECRET,
            expiry=expiry
        )

        # Если токен истёк, пробуем обновить
        if credentials.expired:
            try:
                # Используем адаптер, который возвращает объект с атрибутом data
                credentials.refresh(_requests_request_with_body)
                # Обновляем токен в БД (сохраняем с timezone)
                from django.utils import timezone
                token_obj.access_token = credentials.token
                new_expiry = credentials.expiry
                if new_expiry and not timezone.is_aware(new_expiry):
                    new_expiry = timezone.make_aware(new_expiry)
                token_obj.expires_at = new_expiry
                token_obj.save(update_fields=['access_token', 'expires_at'])
                logger.info(f"Refreshed Google token for user {self.user.id}")
            except RefreshError as e:
                logger.error(f"Failed to refresh token for user {self.user.id}: {e}")
                # Токен невалиден – удаляем его, чтобы пользователь переподключился
                token_obj.delete()
                return None

        return build('calendar', 'v3', credentials=credentials)

    @property
    def is_available(self) -> bool:
        """Проверяет доступность сервиса."""
        return self.service is not None

    def create_event(self, task) -> Optional[str]:
        """
        Создаёт событие в календаре.

        Returns:
            str: ID созданного события или None
        """
        if not self.is_available:
            return None

        event = {
            'summary': task.title,
            'description': task.description or '',
            'start': {
                'dateTime': task.due_date.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': task.due_date.isoformat(),
                'timeZone': 'UTC',
            },
            'reminders': {
                'useDefault': True,
            },
        }

        try:
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            event_id = created_event['id']

            # Сохраняем ID события в задаче
            task.google_event_id = event_id
            task.save(update_fields=['google_event_id'])

            logger.info(f"Created calendar event {event_id} for task {task.id}")
            return event_id
        except Exception as e:
            logger.error(f"Failed to create calendar event for task {task.id}: {e}")
            return None

    def update_event(self, task) -> bool:
        """
        Обновляет событие в календаре.

        Returns:
            bool: True при успехе
        """
        if not self.is_available or not task.google_event_id:
            return False

        event = {
            'summary': task.title,
            'description': task.description or '',
            'start': {
                'dateTime': task.due_date.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': task.due_date.isoformat(),
                'timeZone': 'UTC',
            },
        }

        try:
            self.service.events().update(
                calendarId='primary',
                eventId=task.google_event_id,
                body=event
            ).execute()
            logger.info(f"Updated calendar event {task.google_event_id} for task {task.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update calendar event for task {task.id}: {e}")
            return False

    def delete_event(self, task) -> bool:
        """
        Удаляет событие из календаря.

        Returns:
            bool: True при успехе
        """
        if not self.is_available or not task.google_event_id:
            return False

        try:
            self.service.events().delete(
                calendarId='primary',
                eventId=task.google_event_id
            ).execute()
            logger.info(f"Deleted calendar event {task.google_event_id} for task {task.id}")
            # Очищаем ID в задаче
            task.google_event_id = None
            task.save(update_fields=['google_event_id'])
            return True
        except Exception as e:
            logger.error(f"Failed to delete calendar event for task {task.id}: {e}")
            return False