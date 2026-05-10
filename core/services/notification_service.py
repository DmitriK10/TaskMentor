"""
Сервис отправки push-уведомлений.
Изолирован от других сервисов уведомлений.
"""
import json
import logging
from django.conf import settings
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)


def send_push_notification(user, title, body, data=None):
    """
    Отправляет push-уведомление всем активным подпискам пользователя (Web Push).

    Returns:
        bool: True если хотя бы одно уведомление отправлено успешно
    """
    # Проверяем настройки пользователя
    try:
        if not user.notification_settings.receive_push:
            logger.info(f"Push disabled for user {user.id}")
            return False
    except Exception:
        return False

    from core.models import PushSubscription
    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        logger.info(f"No push subscriptions for user {user.id}")
        return False

    payload = {
        'title': title,
        'body': body,
        'data': data or {},
        'icon': '/static/images/icon.png',
        'badge': '/static/images/badge.png'
    }

    # Получаем vapid claims
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@taskmentor.local')
    vapid_claims = {'sub': f'mailto:{from_email}'}

    # Получаем приватный ключ
    vapid_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
    if not vapid_key:
        logger.error("VAPID_PRIVATE_KEY not configured")
        return False

    success_count = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth,
                    }
                },
                data=json.dumps(payload),
                vapid_private_key=vapid_key,
                vapid_claims=vapid_claims
            )
            success_count += 1
            logger.info(f'Push sent to {sub.endpoint}')
        except WebPushException as e:
            logger.error(f'Push failed for {sub.endpoint}: {e}')
            # Удаляем устаревшие подписки (410 Gone)
            if hasattr(e, 'response') and e.response and e.response.status_code == 410:
                sub.delete()
                logger.info(f'Removed stale subscription {sub.endpoint}')
        except Exception as e:
            logger.error(f'Unexpected error sending push to {sub.endpoint}: {e}')

    return success_count > 0


def cleanup_stale_subscriptions(user):
    """
    Очищает устаревшие push-подписки пользователя.
    Может вызываться периодически.
    """
    from core.models import PushSubscription
    deleted_count, _ = PushSubscription.objects.filter(user=user).delete()
    logger.info(f"Cleaned up {deleted_count} push subscriptions for user {user.id}")
    return deleted_count