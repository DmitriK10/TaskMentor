from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Avg
from datetime import timedelta, datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
import logging

from .models import Client, Task, MoodEntry, NotificationSettings, Goal, PushSubscription, GoogleToken
from .forms import TaskForm, NotificationSettingsForm, GoalForm
from .services.calendar_service import CalendarService
from .services.google_oauth import GoogleOAuthService
from .services.client_analytics_service import ClientAnalyticsFacade
from .services.task_service import TaskService

logger = logging.getLogger(__name__)


# =============================================================================
# ГЛАВНАЯ СТРАНИЦА
# =============================================================================

def index(request):
    return render(request, 'core/index.html')


# =============================================================================
# КЛИЕНТЫ
# =============================================================================

class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'core/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

    def get_queryset(self):
        qs = Client.objects.filter(user=self.request.user)
        search = self.request.GET.get('search', '')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(email__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    fields = ['name', 'email', 'phone', 'birth_date', 'notes']
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('core:client_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ClientDetailView(LoginRequiredMixin, DetailView):
    """
    Представление деталей клиента.
    Использует ClientAnalyticsFacade для получения всех данных.
    """
    model = Client
    template_name = 'core/client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Используем фасад для получения полного контекста
        facade = ClientAnalyticsFacade(self.object)
        analytics_context = facade.get_full_context()

        # Добавляем предзагруженные задачи для оптимизации
        context['all_tasks'] = self.object.tasks.select_related('goal')

        # Объединяем контексты
        context.update(analytics_context)

        return context


class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    fields = ['name', 'email', 'phone', 'birth_date', 'notes']
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('core:client_list')

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)


class ClientDeleteView(LoginRequiredMixin, DeleteView):
    model = Client
    template_name = 'core/client_confirm_delete.html'
    success_url = reverse_lazy('core:client_list')

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)


# =============================================================================
# ЗАДАЧИ
# =============================================================================

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = Task.objects.filter(user=self.request.user).select_related('client')
        filters = self._build_filters()
        qs = self._apply_filters(qs, filters)
        return qs

    def _build_filters(self) -> dict:
        """Собирает фильтры из GET-параметров."""
        return {
            'client_id': self.request.GET.get('client'),
            'status': self.request.GET.get('status'),
            'date_from': self.request.GET.get('date_from'),
            'date_to': self.request.GET.get('date_to'),
            'search': self.request.GET.get('search'),
        }

    def _apply_filters(self, qs, filters: dict):
        """Применяет фильтры к queryset."""
        if filters['client_id']:
            qs = qs.filter(client_id=filters['client_id'])

        if filters['status'] == 'pending':
            qs = qs.filter(completed=False)
        elif filters['status'] == 'completed':
            qs = qs.filter(completed=True)

        if filters['date_from']:
            qs = qs.filter(due_date__date__gte=filters['date_from'])

        if filters['date_to']:
            qs = qs.filter(due_date__date__lte=filters['date_to'])

        if filters['search']:
            qs = qs.filter(
                Q(title__icontains=filters['search']) |
                Q(description__icontains=filters['search'])
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET

        context['clients'] = Client.objects.filter(user=self.request.user)
        context.update({
            'selected_client': params.get('client', ''),
            'selected_status': params.get('status', ''),
            'date_from': params.get('date_from', ''),
            'date_to': params.get('date_to', ''),
            'search': params.get('search', ''),
        })
        return context


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'

    def get_success_url(self):
        return reverse_lazy('core:task_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['client'].queryset = Client.objects.filter(user=self.request.user)
        form.fields['goal'].queryset = Goal.objects.filter(client__user=self.request.user)
        return form

    def form_valid(self, form):
        service = TaskService(self.request.user)
        task_data = {
            'client_id': form.cleaned_data['client'].id,
            'goal_id': form.cleaned_data['goal'].id if form.cleaned_data['goal'] else None,
            'title': form.cleaned_data['title'],
            'description': form.cleaned_data['description'],
            'due_date': form.cleaned_data['due_date'],
            'priority': form.cleaned_data['priority'],
        }
        service.create_task(task_data)
        return redirect(self.get_success_url())


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['client'].queryset = Client.objects.filter(user=self.request.user)
        form.fields['goal'].queryset = Goal.objects.filter(client__user=self.request.user)
        return form

    def get_success_url(self):
        return reverse_lazy('core:task_list')

    def form_valid(self, form):
        service = TaskService(self.request.user)
        task_data = {
            'client_id': form.cleaned_data['client'].id,
            'goal_id': form.cleaned_data['goal'].id if form.cleaned_data['goal'] else None,
            'title': form.cleaned_data['title'],
            'description': form.cleaned_data['description'],
            'due_date': form.cleaned_data['due_date'],
            'priority': form.cleaned_data['priority'],
        }
        service.update_task(self.object, task_data)
        return redirect(self.get_success_url())


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        task = self.get_object()
        service = TaskService(request.user)
        service.delete_task(task)
        return redirect(self.success_url)


@require_POST
def toggle_task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    service = TaskService(request.user)
    service.toggle_complete(task)
    return redirect(request.META.get('HTTP_REFERER', reverse('core:task_list')))


# =============================================================================
# НАСТРОЕНИЕ
# =============================================================================

class MoodEntryCreateView(LoginRequiredMixin, CreateView):
    model = MoodEntry
    fields = ['date', 'mood_score', 'notes']
    template_name = 'core/mood_form.html'

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.kwargs['client_pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(
            Client,
            pk=self.kwargs['client_pk'],
            user=self.request.user
        )
        return context

    def form_valid(self, form):
        client = get_object_or_404(
            Client,
            pk=self.kwargs['client_pk'],
            user=self.request.user
        )
        form.instance.client = client
        return super().form_valid(form)


# =============================================================================
# ПРОФИЛЬ И НАСТРОЙКИ
# =============================================================================

class ProfileView(LoginRequiredMixin, UpdateView):
    """
    Представление профиля пользователя.
    Объединяет настройки уведомлений и информацию о Google Calendar.

    ИСПРАВЛЕНО: добавлен get_context_data с передачей google_connected
    и total_clients в шаблон.
    """
    model = NotificationSettings
    form_class = NotificationSettingsForm
    template_name = 'core/profile.html'
    success_url = reverse_lazy('core:profile')

    def get_object(self, queryset=None):
        # get_or_create гарантирует наличие объекта настроек
        notification_settings, _ = NotificationSettings.objects.get_or_create(
            user=self.request.user
        )
        return notification_settings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Передаём статус подключения Google Calendar в шаблон
        # (используется в profile.html для отображения кнопок)
        context['google_connected'] = GoogleOAuthService.is_connected(self.request.user)
        # Передаём количество клиентов для блока статистики
        context['total_clients'] = Client.objects.filter(user=self.request.user).count()
        return context


# =============================================================================
# ЦЕЛИ
# =============================================================================

class GoalCreateView(LoginRequiredMixin, CreateView):
    model = Goal
    form_class = GoalForm
    template_name = 'core/goal_form.html'

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.kwargs['client_pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(
            Client,
            pk=self.kwargs['client_pk'],
            user=self.request.user
        )
        return context

    def form_valid(self, form):
        client = get_object_or_404(
            Client,
            pk=self.kwargs['client_pk'],
            user=self.request.user
        )
        form.instance.client = client
        return super().form_valid(form)


class GoalUpdateView(LoginRequiredMixin, UpdateView):
    model = Goal
    form_class = GoalForm
    template_name = 'core/goal_form.html'

    def get_queryset(self):
        return Goal.objects.filter(client__user=self.request.user)

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.object.client.pk})


class GoalDeleteView(LoginRequiredMixin, DeleteView):
    model = Goal
    template_name = 'core/goal_confirm_delete.html'

    def get_queryset(self):
        return Goal.objects.filter(client__user=self.request.user)

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.object.client.pk})


# =============================================================================
# PUSH УВЕДОМЛЕНИЯ
# =============================================================================

@require_POST
def subscribe(request):
    """Сохраняет push-подписку пользователя."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    import json
    data = json.loads(request.body)
    endpoint = data.get('endpoint')
    p256dh = data.get('keys', {}).get('p256dh')
    auth = data.get('keys', {}).get('auth')

    if not (endpoint and p256dh and auth):
        return JsonResponse({'error': 'Invalid subscription data'}, status=400)

    PushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=endpoint,
        defaults={'p256dh': p256dh, 'auth': auth}
    )
    return JsonResponse({'status': 'ok'})


def vapid_key(request):
    """Возвращает публичный VAPID ключ."""
    return JsonResponse({'key': settings.VAPID_PUBLIC_KEY})


@require_POST
def register_fcm_token(request):
    """Сохраняет FCM-токен мобильного устройства."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    import json
    data = json.loads(request.body)
    token = data.get('token')
    device_name = data.get('device_name', '')

    if not token:
        return JsonResponse({'error': 'Missing token'}, status=400)

    from core.services.fcm_service import FCMService
    success = FCMService.register_token(request.user, token, device_name)
    if success:
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'error': 'Failed to register token'}, status=500)


@require_POST
def unregister_fcm_token(request):
    """Удаляет FCM-токен."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    import json
    data = json.loads(request.body)
    token = data.get('token')
    if not token:
        return JsonResponse({'error': 'Missing token'}, status=400)

    from core.services.fcm_service import FCMService
    success = FCMService.unregister_token(token)
    return JsonResponse({'status': 'ok' if success else 'error'})


@require_POST
def unsubscribe_all_push(request):
    """Удаляет все push-подписки текущего пользователя."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    deleted_count, _ = PushSubscription.objects.filter(user=request.user).delete()
    return JsonResponse({'status': 'ok', 'deleted': deleted_count})


# =============================================================================
# КАЛЕНДАРЬ
# =============================================================================

class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'core/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clients'] = self.request.user.clients.all()
        context['google_connected'] = GoogleOAuthService.is_connected(self.request.user)
        return context


def calendar_data(request):
    """Возвращает задачи пользователя в формате JSON для FullCalendar."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    start_raw = request.GET.get('start')
    end_raw = request.GET.get('end')

    if not start_raw or not end_raw:
        return JsonResponse({'error': 'Missing start/end'}, status=400)

    # Обрабатываем форматы дат: YYYY-MM-DD и YYYY-MM-DDTHH:MM:SS
    try:
        start_date = datetime.strptime(start_raw[:10], '%Y-%m-%d')
        end_date = datetime.strptime(end_raw[:10], '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    tasks = Task.objects.filter(
        user=request.user,
        due_date__gte=start_date,
        due_date__lt=end_date
    ).select_related('client')

    events = [
        {
            'id': task.id,
            'title': task.title,
            'start': task.due_date.date().isoformat(),
            'end': task.due_date.date().isoformat(),
            'allDay': True,
            'backgroundColor': '#FF8C00' if not task.completed else '#6c757d',
            'extendedProps': {
                'client': task.client.name,
                'completed': task.completed,
            }
        }
        for task in tasks
    ]

    return JsonResponse(events, safe=False)


# =============================================================================
# GOOGLE CALENDAR OAUTH
# =============================================================================

def google_calendar_auth(request):
    """Инициирует авторизацию Google Calendar."""
    try:
        redirect_uri = request.build_absolute_uri(reverse('core:google_callback'))
        oauth_service = GoogleOAuthService(redirect_uri)

        auth_url, state, flow = oauth_service.get_authorization_url(request)
        request.session['oauth_state'] = state
        request.session['oauth_redirect_uri'] = redirect_uri
        return redirect(auth_url)
    except ValueError as e:
        logger.error(f"Google OAuth configuration error: {e}")
        messages.error(
            request,
            'Ошибка конфигурации Google OAuth. '
            'Проверьте переменные окружения GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET.'
        )
        return redirect(reverse('core:profile'))
    except Exception as e:
        logger.error(f"Google OAuth initiation failed: {e}")
        messages.error(request, 'Не удалось инициировать авторизацию Google.')
        return redirect(reverse('core:profile'))


def google_calendar_callback(request):
    """Обрабатывает callback от Google."""
    from google_auth_oauthlib.flow import Flow
    from core.services.google_oauth import GoogleOAuthService

    state = request.session.get('oauth_state')
    redirect_uri = request.session.get('oauth_redirect_uri')

    if not state or not redirect_uri:
        messages.error(request, 'Ошибка авторизации: отсутствует состояние сессии.')
        return redirect(reverse('core:profile'))

    try:
        oauth_service = GoogleOAuthService(redirect_uri)
        flow = Flow.from_client_config(
            oauth_service._get_client_config(),
            scopes=GoogleOAuthService.SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        oauth_service.fetch_and_save_tokens(request, flow)
        messages.success(request, 'Google Calendar успешно подключён!')
        logger.info(f"User {request.user.id} successfully connected Google Calendar")
    except Exception as e:
        logger.exception("Google OAuth callback failed")
        messages.error(request, f'Ошибка при подключении Google Calendar: {str(e)}')
    finally:
        request.session.pop('oauth_state', None)
        request.session.pop('oauth_redirect_uri', None)

    return redirect(reverse('core:profile'))


def google_calendar_disconnect(request):
    """Отключает Google Calendar (удаляет токен)."""
    if not request.user.is_authenticated:
        return redirect(reverse('core:profile'))

    try:
        GoogleOAuthService.revoke_access(request.user)
        messages.success(request, 'Google Calendar отключён.')
    except Exception as e:
        logger.error(f"Error disconnecting Google Calendar: {e}")
        messages.error(request, 'Ошибка при отключении Google Calendar.')

    return redirect(reverse('core:profile'))


# =============================================================================
# CRON ДЛЯ НАПОМИНАНИЙ (унифицированы: только POST + заголовок Authorization)
# =============================================================================

@require_POST
def run_reminders(request):
    """Эндпоинт для вызова напоминаний (защищён CRON_TOKEN)."""
    auth_header = request.headers.get('Authorization', '')
    expected_token = getattr(settings, 'CRON_TOKEN', None)

    if not expected_token:
        logger.error("CRON_TOKEN not set")
        return JsonResponse({'error': 'Server configuration error'}, status=500)

    if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        from django.core.management import call_command
        call_command('send_task_reminders')
        return JsonResponse({'status': 'ok', 'message': 'Reminders sent successfully'})
    except Exception as e:
        logger.exception("Error in run_reminders")
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def run_reassign(request):
    """Эндпоинт для вызова переноса задач (защищён CRON_TOKEN)."""
    auth_header = request.headers.get('Authorization', '')
    expected_token = getattr(settings, 'CRON_TOKEN', None)

    if not expected_token:
        return JsonResponse({'error': 'Server configuration error'}, status=500)

    if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        from django.core.management import call_command
        call_command('reassign_overdue_tasks')
        return JsonResponse({'status': 'ok', 'message': 'Tasks reassigned successfully'})
    except Exception as e:
        logger.exception("Error in run_reassign")
        return JsonResponse({'error': str(e)}, status=500)