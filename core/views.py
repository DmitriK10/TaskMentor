from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from .models import Client, Task, MoodEntry, NotificationSettings, Goal
from .services.notification_service import send_task_creation_notification
from .forms import TaskForm, NotificationSettingsForm, GoalForm
import logging
logger = logging.getLogger(__name__)

# ---------- Новый импорт для эндпоинта ----------
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings

# Главная страница
@login_required
def index(request):
    return render(request, 'index.html')


# ---------- Клиенты ----------
class ClientListView(LoginRequiredMixin, ListView):
    """Список клиентов текущего пользователя"""
    model = Client
    template_name = 'core/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)


class ClientDetailView(LoginRequiredMixin, DetailView):
    """Детальная информация о клиенте, включая историю настроения, прогресс задач и цели"""
    model = Client
    template_name = 'core/client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object

        # Получаем отметки настроения за последние 30 дней
        last_30_days = timezone.now().date() - timedelta(days=30)
        mood_entries = client.mood_entries.filter(date__gte=last_30_days).order_by('-date')
        context['mood_entries'] = mood_entries
        context['mood_data'] = self._get_mood_chart_data(mood_entries)

        # Статистика по задачам (используем метод модели)
        stats = client.get_task_stats()
        context['total_tasks'] = stats['total']
        context['completed_tasks'] = stats['completed']
        context['task_progress_percent'] = stats['percent']

        # Предстоящие задачи (используем метод модели)
        context['upcoming_tasks'] = client.get_upcoming_tasks(limit=5)

        # Цели (прогресс вычисляется свойством модели)
        context['goals'] = client.goals.all()

        return context

    def _get_mood_chart_data(self, mood_entries):
        """
        Подготавливает данные для графика настроения.
        Возвращает список словарей с датами в формате 'dd.mm.yyyy' и оценками.
        """
        data = []
        for entry in mood_entries.order_by('date'):
            data.append({
                'date': entry.date.strftime('%d.%m.%Y'),
                'mood_score': entry.mood_score,
            })
        return data


class ClientCreateView(LoginRequiredMixin, CreateView):
    """Создание нового клиента"""
    model = Client
    template_name = 'core/client_form.html'
    fields = ['name', 'email', 'phone', 'birth_date', 'notes']
    success_url = reverse_lazy('core:client_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ClientUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование клиента"""
    model = Client
    template_name = 'core/client_form.html'
    fields = ['name', 'email', 'phone', 'birth_date', 'notes']
    success_url = reverse_lazy('core:client_list')

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)


class ClientDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление клиента"""
    model = Client
    template_name = 'core/client_confirm_delete.html'
    success_url = reverse_lazy('core:client_list')
    context_object_name = 'client'

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)


# ---------- Задачи ----------
class TaskListView(LoginRequiredMixin, ListView):
    """Список задач с фильтрацией"""
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        queryset = Task.objects.filter(user=self.request.user).select_related('client')
        
        # Фильтрация по GET-параметрам
        client_id = self.request.GET.get('client')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        
        status = self.request.GET.get('status')
        if status == 'completed':
            queryset = queryset.filter(completed=True)
        elif status == 'pending':
            queryset = queryset.filter(completed=False)
        
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(due_date__date__gte=date_from)
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(due_date__date__lte=date_to)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))
        
        return queryset.order_by('due_date', '-priority')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clients'] = Client.objects.filter(user=self.request.user)
        context['selected_client'] = self.request.GET.get('client', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['search'] = self.request.GET.get('search', '')
        return context


class TaskCreateView(LoginRequiredMixin, CreateView):
    """Создание новой задачи"""
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['client'].queryset = Client.objects.filter(user=self.request.user)
        form.fields['goal'].queryset = Goal.objects.filter(client__user=self.request.user)
        return form

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()
        logger.info(f"Task {self.object.id} created by user {self.request.user.id}")
        send_task_creation_notification(self.object)
        return redirect(self.get_success_url())


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование задачи"""
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('core:task_list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['client'].queryset = Client.objects.filter(user=self.request.user)
        form.fields['goal'].queryset = Goal.objects.filter(client__user=self.request.user)
        return form


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление задачи"""
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('core:task_list')
    context_object_name = 'task'

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


@login_required
def toggle_task_complete(request, pk):
    """Переключение статуса задачи (выполнено/не выполнено)"""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.completed = not task.completed
    task.save()
    return redirect('core:task_list')


# ---------- Отметки настроения ----------
class MoodEntryCreateView(LoginRequiredMixin, CreateView):
    """Представление для создания отметки настроения (используется для формы на странице клиента)"""
    model = MoodEntry
    fields = ['date', 'mood_score', 'notes']
    template_name = 'core/moodentry_form.html'  # Шаблон не используется, форма встроена в client_detail.html

    def get_success_url(self):
        # После успешного сохранения возвращаемся на страницу клиента
        return reverse('core:client_detail', kwargs={'pk': self.object.client.pk})

    def form_valid(self, form):
        # Устанавливаем клиента из URL (передаётся через kwargs)
        client = get_object_or_404(Client, pk=self.kwargs['client_pk'], user=self.request.user)
        form.instance.client = client
        return super().form_valid(form)


# ---------- НОВОЕ ПРЕДСТАВЛЕНИЕ ПРОФИЛЯ ----------
class ProfileView(LoginRequiredMixin, TemplateView):
    """Страница профиля пользователя с настройками уведомлений"""
    template_name = 'core/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получаем или создаём настройки уведомлений для текущего пользователя
        settings, created = NotificationSettings.objects.get_or_create(user=self.request.user)
        if 'form' not in context:
            context['form'] = NotificationSettingsForm(instance=settings)
        return context

    def post(self, request, *args, **kwargs):
        settings, created = NotificationSettings.objects.get_or_create(user=request.user)
        form = NotificationSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            return redirect('core:profile')
        return self.render_to_response(self.get_context_data(form=form))


# ---------- Цели ----------
class GoalCreateView(LoginRequiredMixin, CreateView):
    """Создание новой цели для конкретного клиента"""
    model = Goal
    form_class = GoalForm
    template_name = 'core/goal_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.client = get_object_or_404(Client, pk=self.kwargs['client_pk'], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.client = self.client
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.client.pk})


class GoalUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование цели"""
    model = Goal
    form_class = GoalForm
    template_name = 'core/goal_form.html'

    def get_queryset(self):
        # Только цели, принадлежащие клиентам текущего пользователя
        return Goal.objects.filter(client__user=self.request.user)

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.object.client.pk})


class GoalDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление цели"""
    model = Goal
    template_name = 'core/goal_confirm_delete.html'

    def get_queryset(self):
        return Goal.objects.filter(client__user=self.request.user)

    def get_success_url(self):
        return reverse('core:client_detail', kwargs={'pk': self.object.client.pk})


# ---------- ЭНДПОИНТ ДЛЯ EASYCRON ----------
@csrf_exempt
def run_reminders(request):
    """
    Эндпоинт для запуска команды send_task_reminders по расписанию.
    Ожидает заголовок Authorization: Bearer <token> или параметр ?token=...
    """
    # Проверка токена
    auth_header = request.headers.get('Authorization', '')
    token_param = request.GET.get('token', '')
    expected_token = getattr(settings, 'CRON_TOKEN', None)

    if not expected_token:
        logger.error("CRON_TOKEN not set in settings")
        return JsonResponse({'error': 'Server configuration error'}, status=500)

    valid = False
    if auth_header.startswith('Bearer ') and auth_header[7:] == expected_token:
        valid = True
    elif token_param == expected_token:
        valid = True

    if not valid:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    # Запуск команды
    try:
        call_command('send_task_reminders')
        return JsonResponse({'status': 'ok', 'message': 'Reminders sent successfully'})
    except Exception as e:
        logger.exception("Error running reminders")
        return JsonResponse({'error': str(e)}, status=500)