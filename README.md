# TaskMentor – Умный помощник для управления клиентами

Веб-приложение для коучей, психологов, наставников и других специалистов, работающих с клиентами. Позволяет вести клиентскую базу, ставить задачи с приоритетами, отслеживать настроение и прогресс клиентов, получать уведомления (email, Web Push, FCM) и синхронизировать задачи с Google Calendar.

## Функционал

- Аутентификация – вход через Google OAuth 2.0 (django-allauth).
- Управление клиентами – полный CRUD, контактные данные, заметки.
- Управление задачами – создание, редактирование, удаление, привязка к клиенту и цели, приоритеты (высокий/средний/низкий), фильтрация по статусу, дате, клиенту.
- Календарь задач – просмотр задач в виде календаря (FullCalendar) с возможностью перехода к редактированию.
- Отметки настроения – ежедневная шкала 1–10, график динамики за 30 дней, средний балл.
- Цели и прогресс – цели клиента с автоматическим расчётом процента выполнения на основе связанных задач.
- Уведомления – email, Web Push (браузер) и Firebase Cloud Messaging (мобильные). Настройка типа уведомлений в профиле.
- Адаптивный планировщик – автоматический перенос просроченных невыполненных задач на ближайшие свободные дни с учётом максимального количества задач в день (настраивается).
- Интеграция с Google Calendar – создание, обновление и удаление событий в календаре пользователя при работе с задачами.
- Напоминания – командой send_task_reminders (для cron) за час до срока выполнения.
- Многопользовательский режим – каждый пользователь видит только своих клиентов и свои задачи.

## Стек технологий

Backend: Python 3.10+, Django 5.2, django-allauth
База данных: SQLite (разработка), PostgreSQL (продакшен)
Frontend: Bootstrap 5, FullCalendar, Chart.js
Web Push: Service Worker, pywebpush, VAPID
Mobile Push: Firebase Cloud Messaging (FCM), firebase-admin
Google API: Google Calendar API v3, google-api-python-client, google-auth-oauthlib
Сервер: Gunicorn + Whitenoise (статичные файлы)
Деплой: Render / Railway / любой хостинг с поддержкой cron

## Установка и запуск (локальная разработка)

1. Клонирование репозитория
   git clone https://github.com/yourusername/taskmentor.git
   cd taskmentor

2. Создание и активация виртуального окружения
   python -m venv venv
   source venv/bin/activate      # Linux / macOS
   venv\Scripts\activate         # Windows

3. Установка зависимостей
   pip install -r requirements.txt

4. Настройка переменных окружения
   Создайте файл .env в корне проекта. Образец – .env.example.

   Обязательные переменные:
   SECRET_KEY=ваш-секретный-ключ
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost

   # Google OAuth (для входа через Google)
   GOOGLE_CLIENT_ID=ваш-google-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=ваш-google-client-secret

   # Для Google Calendar API (те же значения, что выше)
   GOOGLE_OAUTH2_CLIENT_ID=ваш-google-client-id
   GOOGLE_OAUTH2_CLIENT_SECRET=ваш-google-client-secret

   # Email (для напоминаний)
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=ваша-почта@gmail.com
   EMAIL_HOST_PASSWORD=пароль-приложения
   DEFAULT_FROM_EMAIL=ваша-почта@gmail.com

   # VAPID ключи для Web Push (сгенерировать командой python gen_correct_vapid.py)
   VAPID_PUBLIC_KEY=...
   VAPID_PRIVATE_KEY=...

   # Для FCM (опционально)
   FIREBASE_CREDENTIALS_PATH=полный-путь-к-файлу-сервис-аккаунта.json

   # Токен для защищённых cron-эндпоинтов
   CRON_TOKEN=случайная-длинная-строка

   Где взять Google OAuth credentials?
   - Перейдите в Google Cloud Console.
   - Создайте проект, включите Google People API и Google Calendar API.
   - В разделе «Credentials» создайте OAuth 2.0 Client ID для типа «Web application».
   - Добавьте в «Authorized redirect URIs»:
     http://127.0.0.1:8000/accounts/google/login/callback/
     http://127.0.0.1:8000/core/google/callback/
   - Скопируйте Client ID и Client Secret в .env.

   Генерация VAPID ключей:
   python gen_correct_vapid.py
   Скопируйте вывод в .env (строки VAPID_PUBLIC_KEY и VAPID_PRIVATE_KEY).

5. Применение миграций
   python manage.py migrate

6. Создание суперпользователя (для доступа в админку)
   python manage.py createsuperuser

7. Сбор статичных файлов (только для продакшена, в разработке не требуется)
   python manage.py collectstatic

8. Запуск сервера разработки
   python manage.py runserver

Приложение будет доступно по адресу http://127.0.0.1:8000.

## Настройка дополнительных сервисов

Push-уведомления (Web Push)
- Убедитесь, что в .env заданы VAPID_PUBLIC_KEY и VAPID_PRIVATE_KEY.
- В профиле пользователя включите переключатель «Push-уведомления» и разрешите уведомления в браузере.
- При создании задачи с будущей датой и запуске команды send_task_reminders придёт браузерное уведомление.

Firebase Cloud Messaging (мобильные уведомления)
1. Создайте проект в Firebase Console.
2. Добавьте веб-приложение и/или мобильное приложение.
3. Скачайте файл сервис-аккаунта (Settings -> Service Accounts -> Generate new private key).
4. Укажите путь к этому файлу в .env:
   FIREBASE_CREDENTIALS_PATH=C:/полный/путь/к/firebase-key.json
5. Мобильное приложение должно регистрировать FCM-токен через POST-запрос на /core/fcm/register/.

Google Calendar синхронизация
- После запуска сервера зайдите в профиль (/core/profile/) и нажмите «Подключить Google Calendar».
- Разрешите доступ – после этого все создаваемые/редактируемые/удаляемые задачи будут автоматически синхронизироваться с календарём пользователя.

## Запуск фоновых задач (cron)

Для работы напоминаний и адаптивного планировщика используйте команды:

python manage.py send_task_reminders
python manage.py reassign_overdue_tasks

Настройка cron (Linux/macOS):
* * * * * cd /путь/к/проекту && python manage.py send_task_reminders
0 0 * * * cd /путь/к/проекту && python manage.py reassign_overdue_tasks

На Railway / аналогичных платформах используйте встроенные планировщики (например, railway.json).

## Тестирование

Запуск всех тестов:
python manage.py test core

Запуск тестов только для команд:
python manage.py test core.tests.test_commands

Покрытие тестами: модели, представления, формы, сервисы, команды.

## Деплой (пример для Railway)

1. Создайте проект на Railway, подключите GitHub-репозиторий.
2. Добавьте переменные окружения (из .env) в панели Railway.
3. Установите DATABASE_URL для PostgreSQL (Railway предоставит автоматически).
4. Добавьте файл railway.json в корень проекта (пример уже есть).
5. Убедитесь, что в settings.py для продакшена установлены:
   - DEBUG = False
   - ALLOWED_HOSTS содержит домен Railway.
   - CSRF_TRUSTED_ORIGINS содержит https://*.railway.app.
6. Запустите деплой – Railway выполнит collectstatic и migrate автоматически.

## Лицензия

Проект распространяется под лицензией MIT. Подробнее в файле LICENSE.

## Разработчик

Ваше имя – ваша почта
Репозиторий: https://github.com/yourusername/taskmentor

## Запуск фоновых задач (cron)

Для работы напоминаний и адаптивного планировщика используйте команды:

python manage.py send_task_reminders
python manage.py reassign_overdue_tasks

Или вызывайте защищённые HTTP‑эндпоинты (необходим CRON_TOKEN из .env):

curl -X POST https://your-domain.com/core/cron/run-reminders/ \
  -H "Authorization: Bearer $CRON_TOKEN"

curl -X POST https://your-domain.com/core/cron/reassign-tasks/ \
  -H "Authorization: Bearer $CRON_TOKEN"

На Railway и аналогичных платформах можно использовать встроенные планировщики,
передавая заголовок Authorization, или выполнять команды напрямую (см. railway.json).