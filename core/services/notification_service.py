import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from ..models import NotificationSettings

logger = logging.getLogger(__name__)

def _send_email(task, subject, message):
    """Внутренняя функция для отправки email с проверкой настроек."""
    # Не отправляем для просроченных задач
    if task.due_date <= timezone.now():
        logger.info(f"Task {task.id} is overdue, skipping email")
        return False

    # Получаем или создаём настройки уведомлений
    try:
        settings_obj = task.user.notification_settings
    except NotificationSettings.DoesNotExist:
        settings_obj = NotificationSettings.objects.create(user=task.user)
        logger.info(f"Created missing notification settings for user {task.user.id}")

    if not settings_obj.receive_emails:
        logger.info(f"User {task.user.id} disabled email notifications")
        return False

    from_email = settings.DEFAULT_FROM_EMAIL
    if not from_email:
        from_email = 'noreply@taskmentor.local'
        logger.warning("DEFAULT_FROM_EMAIL not set, using fallback")

    recipient_list = [task.user.email]
    send_mail(subject, message, from_email, recipient_list)
    logger.info(f"Email sent for task {task.id} to {task.user.email}")
    return True

def send_task_creation_notification(task):
    """Отправляет уведомление о создании задачи."""
    subject = f'Новая задача: {task.title}'
    message = f"""
Здравствуйте!

Вы создали задачу для клиента {task.client.name}.
Название: {task.title}
Описание: {task.description or 'нет'}
Срок выполнения: {task.due_date.strftime('%d.%m.%Y %H:%M')}
Приоритет: {task.get_priority_display()}

С уважением,
TaskMentor
"""
    return _send_email(task, subject, message)

def send_task_reminder_notification(task):
    """Отправляет напоминание о задаче за час до срока."""
    subject = f'Напоминание: {task.title} (через час)'
    message = f"""
Здравствуйте!

Напоминаем, что через час истекает срок задачи для клиента {task.client.name}.
Название: {task.title}
Описание: {task.description or 'нет'}
Срок выполнения: {task.due_date.strftime('%d.%m.%Y %H:%M')}
Приоритет: {task.get_priority_display()}

Пожалуйста, не забудьте выполнить задачу.

С уважением,
TaskMentor
"""
    return _send_email(task, subject, message)