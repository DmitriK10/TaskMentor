"""
Сервис для отправки push-уведомлений через Firebase Cloud Messaging (FCM).
"""
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from django.contrib.auth.models import User
from core.models import FCMToken

logger = logging.getLogger(__name__)

# Инициализация Firebase Admin SDK (один раз)
if not firebase_admin._apps:
    cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized")
    else:
        logger.warning("FIREBASE_CREDENTIALS_PATH not set, FCM notifications disabled")


class FCMService:
    """
    Сервис для отправки уведомлений через FCM.
    """

    @staticmethod
    def send_notification(user: User, title: str, body: str, data: dict = None) -> bool:
        """
        Отправляет уведомление на все FCM-токены пользователя.

        Returns:
            bool: True если хотя бы одно уведомление отправлено успешно
        """
        tokens = FCMToken.objects.filter(user=user).values_list('token', flat=True)
        if not tokens:
            logger.info(f"No FCM tokens for user {user.id}")
            return False

        # Проверяем настройки пользователя (можно добавить отдельную настройку receive_fcm)
        try:
            if not user.notification_settings.receive_push:
                logger.info(f"Push disabled for user {user.id}")
                return False
        except Exception:
            pass

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=list(tokens),
        )

        try:
            response = messaging.send_each_for_multicast(message)
            success_count = response.success_count
            logger.info(f"FCM sent to {success_count} of {len(tokens)} devices for user {user.id}")
            # Удаляем недействительные токены
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    token = tokens[idx]
                    if 'not-registered' in str(resp.exception) or 'invalid-registration' in str(resp.exception):
                        FCMToken.objects.filter(token=token).delete()
                        logger.info(f"Removed invalid FCM token: {token}")
            return success_count > 0
        except Exception as e:
            logger.error(f"FCM send failed for user {user.id}: {e}")
            return False

    @staticmethod
    def register_token(user: User, token: str, device_name: str = '') -> bool:
        """
        Сохраняет FCM-токен для пользователя.
        """
        try:
            FCMToken.objects.update_or_create(
                token=token,
                defaults={'user': user, 'device_name': device_name}
            )
            logger.info(f"FCM token registered for user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to register FCM token: {e}")
            return False

    @staticmethod
    def unregister_token(token: str) -> bool:
        """
        Удаляет FCM-токен.
        """
        try:
            FCMToken.objects.filter(token=token).delete()
            logger.info(f"FCM token unregistered")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister FCM token: {e}")
            return False