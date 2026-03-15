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

    # Эндпоинт для EasyCron
    path('cron/run-reminders/', views.run_reminders, name='cron_reminders'),
]