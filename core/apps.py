from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals
        # Инициализируем сервис уведомлений и сохраняем в атрибуте приложения
        from .services.base import create_notification_service
        self.notification_service = create_notification_service()