import os
import sys

# Добавляем путь к проекту в sys.path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Указываем Django settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'taskmentor.settings'

# Активируем виртуальное окружение
activate_this = os.path.join(project_dir, 'venv/bin/activate_this.py')
if os.path.exists(activate_this):
    with open(activate_this) as f:
        exec(f.read(), {'__file__': activate_this})

# Запускаем WSGI-приложение
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()