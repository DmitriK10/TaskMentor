from django import forms
from .models import Client, Task, NotificationSettings, Goal

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['client', 'goal', 'title', 'description', 'due_date', 'priority']
        widgets = {
            'due_date': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                },
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Queryset'ы для полей client и goal будут заполнены в представлении
        self.fields['client'].queryset = Client.objects.none()
        self.fields['goal'].queryset = Goal.objects.none()
        self.fields['client'].widget.attrs.update({'class': 'form-control'})
        self.fields['goal'].widget.attrs.update({'class': 'form-control'})
        self.fields['title'].widget.attrs.update({'class': 'form-control'})
        self.fields['description'].widget.attrs.update({'class': 'form-control', 'rows': 3})
        self.fields['priority'].widget.attrs.update({'class': 'form-select'})


class NotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = NotificationSettings
        fields = ['receive_emails']
        labels = {
            'receive_emails': 'Получать email-напоминания о задачах'
        }


class GoalForm(forms.ModelForm):
    """
    Форма для создания и редактирования цели.
    """
    class Meta:
        model = Goal
        fields = ['title', 'description', 'target_date']
        widgets = {
            'target_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                },
                format='%Y-%m-%d'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].widget.attrs.update({'class': 'form-control'})
        self.fields['description'].widget.attrs.update({'class': 'form-control', 'rows': 3})