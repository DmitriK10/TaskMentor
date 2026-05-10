"""
Сервис для работы с Google OAuth2.
Отделён от логики календаря (SRP).
"""
from dataclasses import dataclass
from typing import Tuple
from django.conf import settings
from django.contrib.auth.models import User
from google_auth_oauthlib.flow import Flow


@dataclass
class GoogleOAuthConfig:
    """Конфигурация Google OAuth."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list


class GoogleOAuthService:
    """
    Сервис для управления OAuth-токенами Google.
    """

    SCOPES = ['https://www.googleapis.com/auth/calendar.events']

    def __init__(self, redirect_uri: str):
        client_id = settings.GOOGLE_OAUTH2_CLIENT_ID
        client_secret = settings.GOOGLE_OAUTH2_CLIENT_SECRET
        if not client_id or not client_secret:
            raise ValueError(
                "Google OAuth2 client ID and secret must be set in settings. "
                "Check GOOGLE_OAUTH2_CLIENT_ID and GOOGLE_OAUTH2_CLIENT_SECRET variables."
            )
        self.config = GoogleOAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=self.SCOPES
        )

    def get_authorization_url(self, request) -> Tuple[str, str, Flow]:
        """
        Генерирует URL для авторизации Google.

        Returns:
            tuple: (authorization_url, state, flow)
        """
        flow = Flow.from_client_config(
            self._get_client_config(),
            scopes=self.config.scopes,
            redirect_uri=self.config.redirect_uri
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return authorization_url, state, flow

    def fetch_and_save_tokens(self, request, flow: Flow) -> bool:
        """
        Получает токены и сохраняет их для пользователя.
        """
        flow.fetch_token(
            authorization_response=request.build_absolute_uri()
        )
        credentials = flow.credentials

        from django.utils import timezone
        from core.models import GoogleToken

        # Преобразуем naive expiry в aware (UTC)
        expiry = credentials.expiry
        if expiry and not timezone.is_aware(expiry):
            expiry = timezone.make_aware(expiry)

        GoogleToken.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'expires_at': expiry,
            }
        )
        return True

    def _get_client_config(self) -> dict:
        """Возвращает конфигурацию клиента для Flow."""
        return {
            "web": {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.config.redirect_uri]
            }
        }

    @staticmethod
    def revoke_access(user: User) -> bool:
        """
        Отзывает доступ пользователя к Google (удаляет токен из БД).
        """
        from core.models import GoogleToken
        try:
            token = user.google_token
            token.delete()
            return True
        except GoogleToken.DoesNotExist:
            return False

    @staticmethod
    def is_connected(user: User) -> bool:
        """Проверяет, подключён ли Google Calendar."""
        return hasattr(user, 'google_token') and user.google_token is not None