# Документ 1. `README_TERMUX.md` (для сервера в Termux)


# 📽 Архитектурная документация: Presentum Server (Termux Edition)

**Presentum** — это персональный движок интерактивных презентаций в реальном времени с поддержкой удалённого управления со смартфона. Построен на архитектуре **Flask + Flask-SocketIO + Gunicorn (gthread) + Poppler (C++) + SQLite**.

Данная документация описывает устройство сервера в Termux, особенности демонизации через Runit, схему туннелирования трафика через Cloudflare и регламент администрирования.

---

## 1. Схема движения трафика

Приложение совмещает фронтенд (Jinja2 SSR, CSS, локальный Socket.IO client), хранилище медиа и бэкенд (REST API + WebSockets). Весь входящий трафик поступает из защищённого туннеля Cloudflare Zero Trust на локальный IPv4-сокет `127.0.0.1:5004`.

```text
[ Лектор / Проектор ]            [ Докладчик / Смартфон ]
        │                                  │
        ▼  (/presentation)                 ▼  (/admin/control)
[ HTTPS / WSS: presentum.andatra.space ]
                    │
                    ▼  (Cloudflare Edge: SSL/TLS, DDoS Protection)
[ Смартфон (Android + Termux) ]
        │
        ├─► [ cloudflared (демон) ] (Принимает входящий туннель)
        │         │
        │         ▼  (Локальный HTTP/WS прокси на http://127.0.0.1:5004)
        └─► [ Gunicorn (демон Runit, worker: gthread) ]
                  │
                  ├──► [ Flask App (Jinja2 SSR + REST API) ]
                  ├──► [ Flask-SocketIO (simple-websocket, threading) ]
                  ├──► [ Poppler / pdftoppm (нарезка PDF) ]
                  └──► [ SQLite: database.db (WAL / timeout=15) ]
```

---

## 2. Разбор компонентов сервера

### A. База данных (SQLite)
* **Файл базы:** `/data/data/com.termux/files/home/Presentum/database.db`
* **Обоснование:** Минимальное потребление памяти и нулевые накладные расходы на поддержание отдельного СУБД-демона.
* **Отказоустойчивость и скорость:**
  - Подключение настроено с `connect_args={"timeout": 15}` для предотвращения блокировок `database is locked` при быстром переключении с пульта.
  - Оптимизированные точечные выборки: состояние слайда формируется через `Slide.query.count()` и быстрый поиск по индексу `filter_by(order_index=idx)` без полной выгрузки таблицы (`.all()`) в память Python.
  - Массовые сдвиги позиций (`order_index`) при вставке и удалении выполняются с `synchronize_session=False`, исключая лишние `SELECT`-запросы перед `UPDATE`.
* **Таблицы:**
  - `slides` — метаданные слайдов, пути к файлам и индексы порядка (`order_index`).
  - `presentation_state` — синглтон-состояние презентации (текущий активный номер слайда, время изменения). Сохраняется между перезагрузками.

### B. WSGI-сервер (Gunicorn + gthread)
* **Запуск:** Многопоточный режим `gthread` (`-w 1 --threads 100`) с поддержкой `simple-websocket`.
* **Порт:** `127.0.0.1:5004` (изолирован от Eventum на `5001`, AmadeusX на `5002` и VoiceTranslator на `8000`).
* **Асинхронность:** `async_mode="threading"` обеспечивает независимую обработку долгоживущих WebSocket-соединений и коротких HTTP-запросов загрузки файлов.
* **Единый контур навигации:** Логика переключения слайдов (`next`, `prev`, `goto`) вынесена в атомарную функцию `navigate()`, устраняя дублирование между REST-ручками и WebSocket-событиями.

### C. Обработка PDF (Poppler / pdftoppm)
* **Пакет:** системный `poppler` (`pkg install poppler`).
* **Принцип:** Конвертация многостраничных PDF в чёткие PNG-слайды выполняется нативным C++ бинарником `pdftoppm -png -r 150` через `subprocess`. Временный PDF гарантированно стирается из памяти/диска сразу после генерации. Никаких тяжёлых Python-биндингов (PyMuPDF/Pillow).

### D. Демонизация (Runit / termux-services)
* **Файл службы:** `$PREFIX/var/service/presentum-backend/run`
* **Содержимое:**
  ```bash
  #!/data/data/com.termux/files/usr/bin/sh
  exec 2>&1
  cd /data/data/com.termux/files/home/Presentum
  exec /data/data/com.termux/files/home/Presentum/venv/bin/gunicorn -w 1 --threads 100 -b 127.0.0.1:5004 app:app
  ```

### E. Сеть и Cloudflare Tunnel
* **Туннель:** `termux-android`.
* **Маршрут:** `presentum.andatra.space` ➔ `http://127.0.0.1:5004`.
* ⚠️ **Критический нюанс (IPv6 таймаут на Android):** В Zero Trust Dashboard адрес origin-сервиса **обязан** быть указан как `http://127.0.0.1:5004`, а **не** `http://localhost:5004`. В Bionic libc Termux `localhost` резолвится первым в IPv6 `::1`, что приводит к 5-секундному зависанию каждого запроса и сбросу WebSocket-рукопожатий.

### F. Профиль энергопотребления и оптимизация под Termux
* **Отключение Reloader (`debug=False`):** В точке входа убран debug-режим Werkzeug, что устраняет второй форк-процесс мониторинга FS. Это экономит ~40–50 МБ RAM и предотвращает постоянные тайм-ауты пробуждения CPU (wakeups).
* **Zero-Poll WebSocket:** Клиенты не спамят сервер запросами — обновление состояния происходит исключительно по push-событию смены слайда. В отсутствие клиентов сетевая активность сервера равна 0 байт/с.
* **Показатели в режиме ожидания (Idle):**
  - **RAM:** ~40–60 МБ (один процесс Gunicorn/Flask).
  - **CPU:** ~0% (процессор смартфона уходит в глубокий сон deep sleep без троттлинга батареи).

---

## 3. Структура проекта

```text
~/Presentum/
├── .env                    # Секретный ключ сессий и пароль администратора
├── database.db             # База данных SQLite (состояние слайдов)
├── app.py                  # Ядро: Flask, Socket.IO, маршруты и API
├── models.py               # Модели Slide и PresentationState
├── slide_service.py        # Сервис сохранения, нарезки PDF и сдвига индексов
├── requirements.txt        # Python-зависимости
├── venv/                   # Виртуальное окружение
│
├── templates/              # HTML-шаблоны (Jinja2 SSR)
│   ├── login.html          # Экран авторизации
│   ├── admin.html          # Панель управления и загрузки слайдов
│   ├── control.html        # Мобильный пульт управления презентацией
│   └── presentation.html   # Полноэкранный экран проектора/лектора
│
└── static/
    ├── js/
    │   └── socket.io.min.js # Локальная библиотека сокетов (zero-CDN)
    └── uploads/
        └── slides/         # Локальные изображения слайдов (PNG/JPG/WEBP)
```

---

## 4. Шпаргалка администратора

### Управление службой в Termux:
* **Статус службы:**
  ```bash
  sv status presentum-backend
  ```
* **Перезапустить бэкенд (после `git pull`):**
  ```bash
  sv restart presentum-backend
  ```
* **Остановить / Запустить:**
  ```bash
  sv down presentum-backend
  sv up presentum-backend
  ```

### Обновление кодовой базы из Git:
```bash
cd ~/Presentum
git pull
sv restart presentum-backend
```

### Резервное копирование и сброс базы:
* **Бэкап базы и слайдов:**
  ```bash
  cp ~/Presentum/database.db ~/database_backup_$(date +%F).db
  tar -czf ~/slides_backup_$(date +%F).tar.gz -C ~/Presentum/static/uploads slides
  ```
* **Полный сброс (чистый старт):**
  ```bash
  rm -f ~/Presentum/database.db
  rm -rf ~/Presentum/static/uploads/slides/*
  sv restart presentum-backend
  ```
