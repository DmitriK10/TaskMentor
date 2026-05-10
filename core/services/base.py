"""
Абстрактный слой для сервисов уведомлений.
Следует принципам SOLID: OCP, DIP.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Protocol, runtime_checkable
from django.contrib.auth.models import User


@dataclass(frozen=True)
class NotificationPayload:
    """
    Единый формат данных для всех уведомлений.
    frozen=True делает объект иммутабельным (безопасность).
    """
    title: str
    body: str
    user: User
    data: Optional[dict] = None
    task_id: Optional[int] = None
    client_name: Optional[str] = None


@runtime_checkable
class NotificationChannel(Protocol):
    """
    Protocol вместо ABC для гибкости типизации.
    Любой класс с этими методами считается каналом уведомлений.
    """

    def send(self, payload: NotificationPayload) -> bool:
        """Отправить уведомление. Возвращает True при успехе."""
        ...

    def is_enabled_for_user(self, user: User) -> bool:
        """Проверить, включён ли канал для пользователя."""
        ...


class EmailChannel:
    """
    Канал email-уведомлений.
    Не наследуется от ABC — использует Protocol для Duck Typing.
    """

    def __init__(self, from_email: Optional[str] = None):
        """DIP: Зависимость внедряется через конструктор, не хардкод."""
        from django.conf import settings
        self._from_email = from_email or getattr(
            settings, 'DEFAULT_FROM_EMAIL', 'noreply@taskmentor.local'
        )

    def is_enabled_for_user(self, user: User) -> bool:
        try:
            return user.notification_settings.receive_emails
        except AttributeError:
            return True  # По умолчанию включено

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_enabled_for_user(payload.user):
            return False

        from django.core.mail import send_mail
        try:
            send_mail(
                subject=payload.title,
                message=payload.body,
                from_email=self._from_email,
                recipient_list=[payload.user.email],
                fail_silently=False
            )
            return True
        except Exception:
            return False


class PushChannel:
    """Канал push-уведомлений (Web Push)."""

    def is_enabled_for_user(self, user: User) -> bool:
        try:
            return user.notification_settings.receive_push
        except AttributeError:
            return False

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_enabled_for_user(payload.user):
            return False

        from .notification_service import send_push_notification
        return send_push_notification(
            user=payload.user,
            title=payload.title,
            body=payload.body,
            data=payload.data
        )


class FCMChannel:
    """Канал push-уведомлений через Firebase Cloud Messaging."""

    def is_enabled_for_user(self, user: User) -> bool:
        try:
            return user.notification_settings.receive_push
        except AttributeError:
            return False

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_enabled_for_user(payload.user):
            return False

        from .fcm_service import FCMService
        return FCMService.send_notification(
            user=payload.user,
            title=payload.title,
            body=payload.body,
            data=payload.data
        )


class SMSChannel:
    """
    Новый канал SMS — добавлен без модификации NotificationService.
    Демонстрация OCP: расширение через добавление, не изменение.
    """

    def __init__(self, sms_gateway=None):
        self._gateway = sms_gateway

    def is_enabled_for_user(self, user: User) -> bool:
        return hasattr(user, 'profile') and getattr(user.profile, 'receive_sms', False)

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_enabled_for_user(payload.user):
            return False

        phone = getattr(payload.user, 'phone', None)
        if not phone:
            return False

        # self._gateway.send(phone, payload.body)
        return True


class NotificationService:
    """
    Фасад для отправки уведомлений.

    OCP: Открыт для расширения (новые каналы), закрыт для модификации.
    DIP: Зависит от абстракции (Protocol), не от конкретики.
    """

    def __init__(self, channels: Optional[List[NotificationChannel]] = None):
        """
        OCP: Каналы передаются снаружи, не хардкодятся.
        """
        self._channels: List[NotificationChannel] = channels or []

    def add_channel(self, channel: NotificationChannel) -> 'NotificationService':
        """Fluent interface для цепочечного добавления каналов."""
        self._channels.append(channel)
        return self

    def notify(self, payload: NotificationPayload) -> dict:
        """
        Отправляет уведомление через все доступные каналы.

        Returns:
            Словарь результатов по каналам.
        """
        results = {}

        for channel in self._channels:
            channel_name = channel.__class__.__name__

            if not channel.is_enabled_for_user(payload.user):
                results[channel_name] = 'disabled'
                continue

            try:
                success = channel.send(payload)
                results[channel_name] = 'sent' if success else 'failed'
            except Exception as e:
                results[channel_name] = f'error: {str(e)}'

        return results

    def notify_task_created(self, task) -> dict:
        """Уведомление о создании задачи."""
        payload = NotificationPayload(
            title=f'Новая задача: {task.title}',
            body=self._format_task_message(task, 'создана'),
            user=task.user,
            task_id=task.id,
            client_name=task.client.name,
            data={'url': f'/core/tasks/{task.id}/update/'}
        )
        return self.notify(payload)

    def notify_task_reminder(self, task) -> dict:
        """Уведомление-напоминание о задаче."""
        payload = NotificationPayload(
            title=f'Напоминание: {task.title} (через час)',
            body=self._format_task_message(task, 'истекает через час'),
            user=task.user,
            task_id=task.id,
            client_name=task.client.name,
            data={'url': f'/core/tasks/{task.id}/update/'}
        )
        return self.notify(payload)

    def _format_task_message(self, task, action: str) -> str:
        return (
            f"Здравствуйте!\n\n"
            f"Задача для клиента {task.client.name} {action}.\n"
            f"Название: {task.title}\n"
            f"Описание: {task.description or 'нет'}\n"
            f"Срок выполнения: {task.due_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"Приоритет: {task.get_priority_display()}\n\n"
            f"Пожалуйста, не забудьте выполнить задачу.\n\n"
            f"С уважением,\nTaskMentor"
        )


def create_notification_service() -> NotificationService:
    """
    Factory function для создания сервиса со стандартным набором каналов.
    Используется в CoreConfig.ready() и как глобальный экземпляр.
    """
    return (NotificationService()
            .add_channel(EmailChannel())
            .add_channel(PushChannel())
            .add_channel(FCMChannel()))


# Глобальный экземпляр сервиса уведомлений.
# Используется в тестах через импорт:
#   from core.services.base import notification_service
# ВАЖНО: в продакшене используйте apps.get_app_config('core').notification_service,
# чтобы гарантировать инициализацию после ready().
notification_service = create_notification_service()