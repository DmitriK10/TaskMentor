from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Клиенты
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/create/', views.ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/update/', views.ClientUpdateView.as_view(), name='client_update'),
    path('clients/<int:pk>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),

    # Задачи
    path('tasks/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/update/', views.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/toggle/', views.toggle_task_complete, name='task_toggle'),

    # Отметки настроения
    path('clients/<int:client_pk>/mood/add/', views.MoodEntryCreateView.as_view(), name='mood_add'),

    # Профиль пользователя (объединённый с настройками уведомлений)
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Цели
    path('clients/<int:client_pk>/goals/create/', views.GoalCreateView.as_view(), name='goal_create'),
    path('goals/<int:pk>/update/', views.GoalUpdateView.as_view(), name='goal_update'),
    path('goals/<int:pk>/delete/', views.GoalDeleteView.as_view(), name='goal_delete'),

    # Push уведомления
    path('push/subscribe/', views.subscribe, name='push_subscribe'),
    path('push/vapid-key/', views.vapid_key, name='vapid_key'),
    path('push/unsubscribe-all/', views.unsubscribe_all_push, name='unsubscribe_all_push'),

    # Календарь
    path('calendar/', views.CalendarView.as_view(), name='calendar'),
    path('calendar/data/', views.calendar_data, name='calendar_data'),

    # Google Calendar
    path('google/auth/', views.google_calendar_auth, name='google_auth'),
    path('google/callback/', views.google_calendar_callback, name='google_callback'),
    path('google/disconnect/', views.google_calendar_disconnect, name='google_disconnect'),

    # Эндпоинты для cron (защищены CRON_TOKEN, теперь только POST)
    path('cron/run-reminders/', views.run_reminders, name='cron_reminders'),
    path('cron/reassign-tasks/', views.run_reassign, name='cron_reassign'),

    # FCM
    path('fcm/register/', views.register_fcm_token, name='fcm_register'),
    path('fcm/unregister/', views.unregister_fcm_token, name='fcm_unregister'),
]