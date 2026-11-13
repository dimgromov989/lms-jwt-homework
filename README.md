# LMS API: JWT и права доступа

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata moderators
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

Откройте /admin/ и добавьте нужного пользователя в группу Moderators.
Права группы на API заданы в контроллерах, поэтому Django admin permissions
для работы API не требуются.

| Маршрут | Действие |
| --- | --- |
| POST /api/users/ | Регистрация: username, email, password |
| POST /api/token/ | Вход: username, password. Ответ содержит access и refresh |
| POST /api/token/refresh/ | Обновление access: refresh |
| GET /api/users/ | Список публичных профилей |
| GET /api/users/{id}/ | Чтение профиля |
| PUT, PATCH, DELETE /api/users/{id}/ | Изменение и удаление своего профиля |
| /api/courses/, /api/lessons/ | Списки, создание, просмотр, изменение и удаление |

Во все защищённые запросы передавайте Authorization: Bearer <access>.
Для курса укажите title и при необходимости description. Для урока также
укажите course (ID курса). Владелец определяется сервером. Урок можно
привязать только к курсу того же владельца. Удаление курса удаляет его уроки.

Обычный пользователь видит и изменяет только свои курсы и уроки.
Модератор читает и редактирует любые, но не создаёт и не удаляет их.
Чужие профили содержат только id, username и first_name. Пароль не
возвращается в ответах. Платёжные данные в проекте не хранятся.

Для запуска вне локального окружения задайте DJANGO_DEBUG=0,
DJANGO_SECRET_KEY и DJANGO_ALLOWED_HOSTS через переменные окружения.

В названии и описании курса или урока разрешён обычный текст и ссылки
на youtube.com и его поддомены. Списки курсов и уроков поддерживают
`?page=2&page_size=5`. По умолчанию возвращается 10 записей, максимум 50.

Подписка оформляется запросом `POST /api/courses/{id}/subscription/` без тела
и удаляется запросом `DELETE` на тот же адрес. Повторный POST возвращает
существующую подписку, DELETE без подписки возвращает 404. Подписаться можно
на любой существующий курс по его ID. Права чтения и редактирования курса
проверяются отдельно. В списке и карточке курса `is_subscribed` относится
только к текущему пользователю.

Отчёт о покрытии сохранён в `coverage.txt`. Для повторной проверки:

```powershell
python -m pip install -r requirements-dev.txt
python -m coverage run --source=lms,config manage.py test
python -m coverage report -m --omit="*/tests.py" > coverage.txt
```
