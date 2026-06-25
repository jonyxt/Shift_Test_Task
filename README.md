# Booking service

Тестовое задание для сервиса бронирования переговорных комнат.

Приложение написано на FastAPI. Данные хранятся в PostgreSQL, работа с базой идет через асинхронный SQLAlchemy. Авторизация сделана через JWT-токены.

## Что умеет сервис

- регистрация и авторизация пользователей;
- автоматическое назначение роли `admin` первому зарегистрированному пользователю;
- обычные пользователи получают роль `employee`;
- просмотр своего профиля;
- просмотр списка пользователей администратором;
- обновление профиля пользователя;
- защита от удаления последнего администратора;
- просмотр переговорных комнат;
- просмотр свободных слотов на выбранную дату;
- создание бронирования;
- просмотр своих бронирований;
- просмотр всех бронирований администратором;
- фильтрация всех бронирований по дате;
- отмена бронирования;
- запрет двойного активного бронирования одного и того же слота.

При запуске приложение само создает таблицы и добавляет стартовые комнаты со слотами, если они еще не были созданы.

## Стек

- Python 3.13
- FastAPI
- Uvicorn
- PostgreSQL
- SQLAlchemy async
- asyncpg
- Pydantic
- PyJWT
- bcrypt
- Poetry
- Docker / Docker Compose
- pytest
- httpx

## Структура проекта

```text
app/
  app.py            # FastAPI-приложение и endpoint
  auth.py           # JWT, хеширование паролей, dependencies авторизации
  config.py         # чтение переменных окружения
  database.py       # engine, sessionmaker, Base
  dependencies.py   # общие FastAPI dependencies
  lifespan.py       # действия при старте и остановке приложения
  models.py         # SQLAlchemy-модели
  schemas.py        # Pydantic-схемы
  services.py       # бизнес-логика

tests/
  test_api.py       # интеграционные тесты API

Dockerfile
docker-compose.yml
pyproject.toml
poetry.lock
.env.example
```

## Переменные окружения

Для запуска нужен файл `.env` в корне проекта.

Пример содержимого хранится в .env.example:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=booking_db
POSTGRES_HOST=localhost
POSTGRES_PORT=3223

JWT_SECRET=change_me_to_random_secret
JWT_ALGORITHM=HS256
JWT_EXP_DELTA_SECONDS=3600
```

Пояснение по переменным:

- `POSTGRES_USER` - пользователь PostgreSQL;
- `POSTGRES_PASSWORD` - пароль PostgreSQL;
- `POSTGRES_DB` - имя основной базы данных;
- `POSTGRES_HOST` - хост базы для локального запуска без Docker;
- `POSTGRES_PORT` - порт PostgreSQL на хосте;
- `JWT_SECRET` - секрет для подписи JWT-токенов;
- `JWT_ALGORITHM` - алгоритм подписи JWT;
- `JWT_EXP_DELTA_SECONDS` - время жизни токена в секундах.

При запуске через Docker Compose для приложения внутри контейнера хост базы переопределяется на `db`, а порт на `5432`.

`POSTGRES_PORT=3223` используется как внешний порт PostgreSQL на компьютере. Внутри Docker-сети PostgreSQL все равно работает на стандартном порту `5432`.


## Запуск через Docker Compose

Основной способ запуска:

```bash
docker compose up --build
```

После запуска приложение будет доступно по адресу:

```text
http://localhost:8000
```

Swagger UI:

```text
http://localhost:8000/docs
```

OpenAPI JSON:

```text
http://localhost:8000/openapi.json
```

Остановить контейнеры:

```bash
docker compose down
```

Важно: обычный `docker compose down` не удаляет данные основной базы, потому что для PostgreSQL используется volume `postgres_data`.

Если нужно полностью удалить данные основной базы:

```bash
docker compose down -v
```

## Запуск через Dockerfile и docker run

Этот вариант нужен, если нужно запустить только контейнер приложения без Docker Compose.

Перед запуском через `docker run` PostgreSQL должен быть уже запущен отдельно. Также в PostgreSQL должна существовать база, указанная в `.env`.

Если в `.env` указано:

```env
POSTGRES_DB=booking_db
```

то база `booking_db` должна быть создана заранее. Если базы нет, приложение не сможет подключиться к PostgreSQL и завершит запуск с ошибкой.

Пример создания базы:

```bash
createdb -h localhost -p 3223 -U postgres booking_db
```

После этого нужно собрать Docker-образ приложения:

```bash
docker build -t booking-service .
```

Запуск приложения:

```bash
docker run --rm -p 8000:8000 `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=booking_db `
  -e POSTGRES_HOST=host.docker.internal `
  -e POSTGRES_PORT=3223 `
  -e JWT_SECRET=change_me_to_random_secret `
  -e JWT_ALGORITHM=HS256 `
  -e JWT_EXP_DELTA_SECONDS=3600 `
  booking-service
```

Если PostgreSQL запущен локально на стандартном порту `5432`, то в команде нужно указать:

```bash
POSTGRES_PORT=5432
```

А базу создать так:

```bash
createdb -h localhost -p 5432 -U postgres booking_db
```

## Запуск тестов через Docker Compose

Для тестов в `docker-compose.yml` есть отдельный профиль `test`.

Тесты запускают отдельное приложение `test_app` и отдельную базу `test_db`, чтобы не портить данные основной базы.

Команда:

```bash
docker compose --profile test up --build --abort-on-container-exit --exit-code-from tests
```

После завершения тестов можно удалить тестовые контейнеры:

```bash
docker compose --profile test rm -sf test_app test_db tests
```

Тестовая база не использует постоянный volume, поэтому после удаления контейнера данные тестовой базы не сохраняются.

## Локальный запуск без Docker

Этот вариант возможен только если PostgreSQL уже установлен и запущен локально.

Перед запуском приложения база из `.env` должна уже существовать. Если в `.env` указано:

```env
POSTGRES_DB=booking_db
```

то в PostgreSQL должна быть создана база `booking_db`.

Пример создания базы через `createdb`:

```bash
createdb -h localhost -p 5432 -U postgres booking_db
```

Если локальный PostgreSQL работает на стандартном порту `5432`, для локального запуска через Poetry в `.env` нужно указать:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

Установка зависимостей:

```bash
poetry install
```

Запуск приложения:

```bash
poetry run uvicorn app.app:app --reload
```

При локальном запуске приложение берет настройки из `.env`.

## Роли пользователей

В сервисе есть две роли:

- `admin` - администратор;
- `employee` - обычный сотрудник.

Первый зарегистрированный пользователь автоматически становится администратором. Все следующие пользователи создаются с ролью `employee`.

Администратор может:

- смотреть список всех пользователей;
- смотреть пользователя по id;
- изменять данные любого пользователя;
- менять роли пользователей;
- смотреть все бронирования;
- фильтровать все бронирования по дате;
- отменять любые бронирования.

Сотрудник может:

- смотреть свой профиль;
- изменять свой профиль;
- смотреть комнаты;
- смотреть доступные слоты;
- создавать бронирования;
- смотреть только свои бронирования;
- отменять только свои бронирования.

В коде есть проверка, которая не позволяет снять роль администратора с последнего администратора в системе.

## Основные endpoint

### Авторизация

```text
POST /register
POST /login
```

Регистрация:

```json
{
  "username": "admin_user",
  "password": "password123",
  "email": "admin@example.com",
  "phone": null
}
```

Ответ:

```json
{
  "id": 1,
  "username": "admin_user",
  "email": "admin@example.com",
  "phone": null,
  "role": "admin"
}
```

Логин:

```json
{
  "username": "admin_user",
  "password": "password123"
}
```

Ответ:

```json
{
  "access_token": "jwt_token",
  "token_type": "bearer"
}
```

Для защищенных запросов токен передается в заголовке:

```text
Authorization: Bearer jwt_token
```

### Пользователи

```text
GET /users/self
GET /users
GET /users/{user_id}
PATCH /users/{user_id}
```

`GET /users` и `GET /users/{user_id}` доступны только администратору.

Пример частичного обновления пользователя:

```json
{
  "phone": "79999999999"
}
```

Поля, которые не переданы в запросе, не изменяются.

### Комнаты

```text
GET /rooms
GET /rooms/{room_id}
GET /rooms/available/{date}
```

Пример:

```text
GET /rooms/available/2030-01-15
```

Ответ содержит комнаты и свободные временные слоты на выбранную дату.

### Бронирования

```text
POST /bookings
GET /bookings
GET /bookings/{booking_id}
GET /bookings/all
PATCH /bookings/cancel/{booking_id}
```

Создание бронирования:

```json
{
  "room_id": 1,
  "time_window_id": 1,
  "date": "2030-01-15"
}
```

`GET /bookings` возвращает бронирования текущего пользователя.

`GET /bookings/all` доступен только администратору. Можно передать дату query-параметром:

```text
GET /bookings/all?date=2030-01-15
```

Отмена бронирования:

```text
PATCH /bookings/cancel/1
```

Бронирование не удаляется из базы. У него меняется флаг `is_active`, заполняются данные об отмене, а слот снова становится доступным для новой брони.

## Стартовые комнаты и слоты

При первом запуске создаются три комнаты:

- Большой конференц зал - до 25 человек;
- Средний конференц зал - до 15 человек;
- Малый конференц зал - до 8 человек.

Для каждой комнаты создаются слоты:

- 09:00-12:00;
- 13:00-16:00;
- 16:00-19:00.

Если комнаты уже есть в базе, стартовые данные повторно не добавляются.

## Что проверяют тесты

Тесты находятся в `tests/test_api.py` и работают через реальные HTTP-запросы к запущенному приложению.

Проверяются основные сценарии:

- доступность OpenAPI;
- регистрация первого администратора;
- регистрация пользователя;
- логин;
- получение текущего пользователя;
- права администратора на просмотр пользователей;
- запрет сотруднику смотреть и менять чужие данные;
- доступ к комнатам только с токеном;
- получение доступных слотов;
- создание бронирования;
- просмотр своих бронирований;
- запрет просмотра чужой брони сотрудником;
- отмена своей брони;
- запрет отмены чужой брони сотрудником;
- запрет двойного активного бронирования одного слота;
- освобождение слота после отмены;
- просмотр всех бронирований администратором;
- фильтрация бронирований по дате;
- отмена чужой брони администратором.