from django.contrib import admin
from .models import Client, Task, MoodEntry, Goal

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name', 'email', 'phone')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'due_date', 'priority', 'completed', 'goal')
    list_filter = ('completed', 'priority', 'user', 'goal')
    search_fields = ('title', 'client__name')

@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ('client', 'date', 'mood_score')
    list_filter = ('client', 'date')

@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'target_date', 'created_at')
    list_filter = ('client',)
    search_fields = ('title', 'client__name')