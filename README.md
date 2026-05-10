## Запуск фоновых задач (cron)

Для работы напоминаний и адаптивного планировщика используйте команды:

python manage.py send_task_reminders
python manage.py reassign_overdue_tasks

Либо вызывайте защищённые HTTP‑эндпоинты (необходим CRON_TOKEN из .env):

curl -X POST https://your-domain.com/core/cron/run-reminders/ \
  -H "Authorization: Bearer $CRON_TOKEN"

curl -X POST https://your-domain.com/core/cron/reassign-tasks/ \
  -H "Authorization: Bearer $CRON_TOKEN"

На Railway / аналогичных платформах используйте встроенные планировщики  
с поддержкой HTTP‑запросов, передавая заголовок Authorization.