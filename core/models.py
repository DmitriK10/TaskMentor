from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Client(models.Model):
    """
    Модель клиента специалиста.
    Связана с пользователем (специалистом) через ForeignKey.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='clients',
        verbose_name='Специалист'
    )
    name = models.CharField(max_length=100, verbose_name='Имя')
    email = models.EmailField(blank=True, verbose_name='Email')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    birth_date = models.DateField(null=True, blank=True, verbose_name='Дата рождения')
    notes = models.TextField(blank=True, verbose_name='Заметки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'

    def __str__(self):
        return self.name

    def get_task_stats(self):
        """Возвращает статистику задач клиента."""
        tasks = self.tasks.all()
        total = tasks.count()
        completed = tasks.filter(completed=True).count()
        return {
            'total': total,
            'completed': completed,
            'percent': int(completed / total * 100) if total > 0 else 0
        }

    def get_upcoming_tasks(self, limit=5):
        """Возвращает предстоящие невыполненные задачи (ограниченное количество)."""
        from django.utils import timezone
        return self.tasks.filter(
            completed=False,
            due_date__date__gte=timezone.now().date()
        ).order_by('due_date')[:limit]


class Task(models.Model):
    """
    Модель задачи, привязанной к клиенту.
    """
    PRIORITY_CHOICES = [
        ('high', 'Высокий'),
        ('medium', 'Средний'),
        ('low', 'Низкий'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='Специалист'
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='Клиент'
    )
    goal = models.ForeignKey(
        'Goal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='Цель'
    )
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    due_date = models.DateTimeField(verbose_name='Срок выполнения')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name='Приоритет')
    completed = models.BooleanField(default=False, verbose_name='Выполнена')
    reminder_sent = models.BooleanField(default=False, verbose_name='Напоминание отправлено')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        ordering = ['due_date', '-priority']
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'

    def __str__(self):
        return self.title


class MoodEntry(models.Model):
    """
    Модель отметки настроения клиента.
    """
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='mood_entries',
        verbose_name='Клиент'
    )
    date = models.DateField(verbose_name='Дата')
    mood_score = models.PositiveSmallIntegerField(
        verbose_name='Оценка настроения',
        help_text='Оценка от 1 до 10'
    )
    notes = models.TextField(blank=True, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        ordering = ['-date']
        unique_together = ['client', 'date']
        verbose_name = 'Отметка настроения'
        verbose_name_plural = 'Отметки настроения'

    def __str__(self):
        return f"{self.client.name} - {self.date} - {self.mood_score}"


class NotificationSettings(models.Model):
    """
    Настройки уведомлений для пользователя.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_settings',
        verbose_name='Пользователь'
    )
    receive_emails = models.BooleanField(
        default=True,
        verbose_name='Получать email-уведомления'
    )

    class Meta:
        verbose_name = 'Настройки уведомлений'
        verbose_name_plural = 'Настройки уведомлений'

    def __str__(self):
        return f'Настройки для {self.user.email}'


class Goal(models.Model):
    """
    Цель клиента. Связана с конкретным клиентом.
    """
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='goals',
        verbose_name='Клиент'
    )
    title = models.CharField(max_length=200, verbose_name='Название цели')
    description = models.TextField(blank=True, verbose_name='Описание')
    target_date = models.DateField(null=True, blank=True, verbose_name='Целевая дата')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        ordering = ['target_date', 'title']
        verbose_name = 'Цель'
        verbose_name_plural = 'Цели'

    def __str__(self):
        return f"{self.client.name} – {self.title}"

    @property
    def progress_percent(self):
        """Возвращает процент выполнения цели на основе связанных задач."""
        total = self.tasks.count()
        if total == 0:
            return 0
        completed = self.tasks.filter(completed=True).count()
        return int(completed / total * 100)