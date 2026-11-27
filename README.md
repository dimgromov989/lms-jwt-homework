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

В названии и описании курса или урока разрешены обычный текст и ссылки
на youtube.com и его поддомены. У урока есть необязательное поле `video_url`
для HTTP(S)-ссылки, например `https://www.youtube.com/watch?v=abc123`.
При ссылке на сторонний сайт API возвращает 400 с ошибкой в соответствующем поле.
Списки курсов и уроков поддерживают
`?page=2&page_size=5`. По умолчанию возвращается 10 записей, максимум 50.

`POST /api/courses/{id}/subscription/` без тела переключает подписку текущего пользователя.
Первый запрос создаёт подписку и возвращает 201, повторный снимает её и возвращает 200.
В обоих ответах есть сообщение `detail` и новое значение `is_subscribed`.
Для явной отписки также доступен `DELETE` по тому же адресу. При отсутствии подписки он возвращает 404.
Подписаться можно на любой существующий курс по его ID. В списке доступных курсов
и в карточке курса `is_subscribed` показывает подписку пользователя, выполнившего запрос.

Для проверки в Postman запустите локальный сервер, импортируйте
[коллекцию подписок](postman/subscriptions.postman_collection.json) и выполните её целиком в Collection Runner.
Переменная `baseUrl` по умолчанию указывает на `http://127.0.0.1:8000`.
Коллекция регистрирует временного пользователя, получает JWT, проверяет подписку в карточке
и списке курсов, снимает подписку и удаляет созданные данные.

Отчёт о покрытии сохранён в `coverage.txt`. Для повторной проверки:

```powershell
python -m pip install -r requirements-dev.txt
python -m coverage run --source=lms,config manage.py test
python -m coverage report -m --omit="*/tests.py" > coverage.txt
```
