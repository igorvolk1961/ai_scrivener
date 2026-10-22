# Инженерные правила и локальная проверка

## 1. Источник истины

| Что | Где |
|---|---|
| Функциональные и нефункциональные требования | `docs/requirements/requirements.yaml` |
| Сгенерированные FR/NFR | `docs/requirements/functional_requirements.md`, `docs/requirements/nonfunctional_requirements.md` |
| Матрица трассируемости | `docs/requirements/traceability_matrix.md` |
| Числовые параметры | `config/parameters.yaml` |
| Схема числовых параметров | `config/parameters.schema.json` |

`requirements.yaml` — единственное место, где редактируются требования. Markdown-документы и матрица генерируются командой `make requirements`; вручную их не редактируют. Пре-коммит проверяет, что сгенерированные файлы актуальны.

Новые требования добавляются со статусом `approval: proposed` и становятся обязательными только после согласования. Изменение существующего требования фиксируется в истории Git.

## 2. Числовые параметры

Все настраиваемые числовые параметры — лимиты, таймауты, повторы, пороги, интервалы, размеры пакетов, порты, температуры, размерности и лимиты токенов — хранятся в `config/parameters.yaml`.

Правила:

- В коде нет числовых значений этих параметров.
- Код читает параметры через единый загрузчик конфигурации.
- Схема `config/parameters.schema.json` запрещает неизвестные ключи и проверяет диапазоны.
- Перекрёстные проверки (например, `chunk_overlap_chars < chunk_size_chars`, длина backoff не меньше числа повторов) выполняются валидатором.
- Протокольные и алгоритмические константы (например, HTTP-коды, индексы массивов) не являются настраиваемыми параметрами. Они допускаются в коде и не выносятся в конфиг; это осознанное исключение, чтобы не превращать код в набор бессмысленных ссылок.
- Инструментальные скрипты в `scripts/` и тесты используют структурные числа (коды возврата, индексы, тестовые данные). Они не являются параметрами приложения и не выносятся в конфиг.
- Для Python запрещены магические числа в сравнениях (ruff `PLR2004`) и числовые значения известных параметров (локальный чекер).
- Для BSL включается диагностика `MagicNumber` в BSL Language Server.

## 3. Локальные секреты

Исходный файл ключей — `.env_0`; он не коммитится. Из него локально формируются:

- `rag-service/.env` — GigaChat, service-token, Qdrant;
- `.env` — DeepSeek для будущей интеграции 1С.

Оба файла игнорируются Git. Реальные значения в документацию и тесты не попадают. Для проверки compose использовать `docker compose ... config --quiet`: обычный `config` печатает значения переменных.

## 4. Заглушки

В production-коде запрещены `TODO`, `FIXME`, `XXX`, `HACK`, `NotImplementedError`, `заглушка` и аналогичные маркеры. Локальный чекер блокирует их в `src`, `rag-service/src` и `scripts`. Если заглушка действительно нужна, она сначала согласуется как отдельное требование.

## 5. Установка

Требования: системный Python 3.12, uv, Docker, pre-commit, 1C:EDT 2026.1.3, платформа 1С:Предприятие 8.3.27 Community, демо-база 1С:Документооборот 2.1.38.11 из `DocMng_2_1_38_11_new.dt`.

В `pyproject.toml` включён `python-preference = "only-system"`: uv-managed интерпретатор в текущей среде даёт сбой `hashlib`/`pre-commit`. Используется системный Python 3.12.

```bash
uv sync
uv run pre-commit install
```

Для BSL-проверки установить `bsl-language-server` и добавить его в `PATH`. Без него пре-коммит с BSL-файлами завершится ошибкой с указанием дальнейших действий.

## 6. Команды

```bash
make requirements   # перегенерировать FR/NFR и матрицу
make lint           # все пре-коммит-хуки
make test           # pytest
make check          # requirements + lint + test
```

## 7. Пре-коммит

Настроены:

- общие проверки YAML/JSON, больших файлов, пробелов, merge-конфликтов, приватных ключей;
- `ruff` и `ruff-format`;
- `mypy` в strict-режиме для `scripts` и `tests`;
- `yamllint`;
- валидация `config/parameters.yaml` по JSON-схеме;
- проверка требований и матрицы трассируемости;
- запрет заглушек;
- запрет хардкода числовых параметров;
- BSL Language Server с диагностикой `MagicNumber`;
- быстрые тесты `pytest`.

## 8. Тесты

- Поведенческие тесты обязательны для каждого модуля.
- Внешние сервисы (DeepSeek, GigaChat, Qdrant) изолируются mock/respx/локальным Qdrant.
- Тесты не требуют реальных секретов и сети.
- Для 1С-кода используются сценарные тесты и проверка конфигурации в EDT/Конфигураторе.
- Тестовые идентификаторы в матрице имеют вид `TEST-FR-XXX-NN` или `TEST-NFR-XXX-NN`.

## 9. Проверка 1С

1. Восстановить демо-базу из `DocMng_2_1_38_11_new.dt` в отдельную файловую базу (см. раздел 12).
2. Открыть расширение в 1C:EDT 2026.1.3 и выполнить `build`/`validate`.
3. В Конфигураторе на демо-базе выполнить `CheckConfig`.
4. Собрать `.cfe`, применить к чистой копии демо-базы и убедиться, что базовая конфигурация не изменилась.
5. Прогнать сценарные тесты из `docs/requirements/traceability_matrix.md`.

## 10. Установка 1C:EDT

Установщик 1C:EDT требует прав администратора. Дистрибутив распакован в `~/.local/share/1c-edt-installer`.

```bash
sudo bash scripts/setup/install_edt.sh
```

После установки запускается `1C:EDT Start`; для загрузки самого EDT нужен вход в аккаунт 1С и установка продукта в окне EDT Start. Продукты устанавливаются в `~/.local/share/1C/1cedtstart/installations`.

Установленный EDT: `~/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedt`, версия 2026.1.3.

Запуск с JavaFX-совместимым JDK:

```bash
"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedt" \
  -vm /opt/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/java \
  -data /home/igorvolk/.edt-workspace/ai_scrivener_ide
```

`-vm` обязателен: системный `/usr/bin/java` не содержит JavaFX, и EDT завершается с ошибкой «Поддержка JavaFX не установлена».

Базовая конфигурация импортируется в отдельное рабочее пространство EDT и не коммитится. Расширение создаётся в проекте `ai_scrivener` и привязывается к базовой конфигурации.

Порядок:

1. Восстановить демо-базу из `.dt` (раздел 12).
2. Импортировать базовую конфигурацию в EDT: `File → Import → 1C:Enterprise → Configuration` или CLI-командой `import` по XML-выгрузке базы.
3. Создать расширение `ai_scrivener`, привязанное к базовой конфигурации; префикс `АИС_`; режим совместимости равен режиму совместимости базы.
4. Проверить пустое расширение командами `build` и `validate`.

Проверка расширения:

```bash
"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/ai_scrivener_cli \
  -timeout 300 \
  -command build --project-list /home/igorvolk/PycharmProjects/ai_scrivener

"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/ai_scrivener_cli \
  -timeout 180 \
  -command validate --file /tmp/kilo/validate_ai_scrivener.tsv \
  --project-list /home/igorvolk/PycharmProjects/ai_scrivener
```

Пустой TSV-отчёт означает отсутствие ошибок. Команды `build` и `validate` проверяют модель EDT; `CheckConfig` и применение `.cfe` выполняются на локальной демо-базе (раздел 12).

## 11. RAG-сервис

```bash
uv sync --project rag-service
uv run --project rag-service pytest -c rag-service/pyproject.toml rag-service/tests
uv run --project rag-service mypy
uv run --project rag-service ruff check --force-exclude
```

Запуск локально:

```bash
cp rag-service/.env.example rag-service/.env
uv run --project rag-service python -m rag_service
```

`rag-service/.env` содержит только строковые параметры и секреты. Все числовые параметры сервис читает из `config/parameters.yaml`.

Для GigaChat используется модель `EmbeddingsGigaR` (размерность 2560) и публичный корневой сертификат `config/russian_trusted_root_ca.pem`. Путь задаётся в `RAG_GIGACHAT_CA_BUNDLE`; TLS-проверка не отключается.

Docker Compose:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## 12. Локальный стенд Документооборота

Источники:

- дистрибутив базы: `/home/igorvolk/Загрузки/DocMng_2_1_38_11_new.zip`;
- выгрузка базы: `DocMng_2_1_38_11_new.dt`;
- дистрибутив платформы: `/home/igorvolk/Загрузки/server64_8_3_27_2342.zip`;
- рабочая база: `/home/igorvolk/1C/ai_scrivener_docmng`.

Порядок:

1. Установить платформу 8.3.27 Community из `server64_8_3_27_2342.zip` с правами администратора; проверить `1cv8`, `1cv8c` и Конфигуратор. Платформа установлена в `/opt/1cv8/x86_64/8.3.27.2342`.
2. Активировать лицензию 1С для установленной платформы. Без действующей лицензии `1cv8 DESIGNER /RestoreIB` завершается сообщением «Не найдена лицензия. Не обнаружен ключ защиты программы или полученная программная лицензия!».
3. Распаковать архив базы и восстановить `.dt` в отдельную файловую базу. Не восстанавливать поверх существующей базы.
4. Открыть базу в Конфигураторе и зафиксировать имя конфигурации, версию, редакцию (ПРОФ/КОРП), режим совместимости и ограничения демо-режима.
5. Импортировать базовую конфигурацию в EDT, создать расширение `ai_scrivener` с префиксом `АИС_` и режимом совместимости базы.
6. Собрать `.cfe` и применить к копии демо-базы; проверить, что базовая конфигурация не изменилась.

Вторая выгрузка `DocMng_2_1_37_5_new.dt` используется только для проверки совместимости по отдельному требованию.

Ограничения: коммерческой лицензии на Документооборот нет; демо-режим может ограничивать число пользователей, срок работы и функциональность. Стенд предназначен для разработки и проверки, не для промышленной эксплуатации.

### 12.1. Активация community-лицензии

Community-лицензия — это «Лицензия для разработчиков» 1С:Предприятие 8.3. Она бесплатна, но требует полной регистрации на портале разработчика и действует только для разработки, отладки и тестирования. Это не учебная версия: платформа полнофункциональная, но с ограничениями (не более 3 прямых сеансов, 1 веб-сеанс, водяной знак «Версия для разработчиков»).

1. Зарегистрируйтесь или войдите на `https://developer.1c.ru/`. Регистрация должна быть полной, с подтверждением номера телефона.
2. Убедитесь, что установлена платформа 8.3.23 или новее. В проекте используется 8.3.27: `/opt/1cv8/x86_64/8.3.27.2342`.
3. Запустите клиент от пользователя `igorvolk`, не через `sudo`:
   ```bash
   /opt/1cv8/x86_64/8.3.27.2342/1cv8
   ```
4. В окне выбора информационной базы нажмите **«Получить лицензию»**. Если кнопки нет, откройте меню **«Сервис» → «Получение лицензии»**. Если лицензия уже установлена, но не работает — **«Сервис» → «Установка лицензии»**.
5. Выберите **«Лицензия для разработчиков»** (community), а не учебную и не базовую.
6. Введите логин и пароль от `developer.1c.ru`. При необходимости заполните форму (ФИО, email, телефон) и подтвердите согласие.
7. Дождитесь сообщения об успешной установке. Файл `.lic` обычно сохраняется в `~/.1cv8/1C/1cv8/conf/`; точный путь показывает диалог установки.
8. Проверьте лицензию восстановлением базы:
   ```bash
   /opt/1cv8/x86_64/8.3.27.2342/1cv8 DESIGNER \
     /F/home/igorvolk/1C/ai_scrivener_docmng \
     /RestoreIB /tmp/kilo/docmng/DocMng_2_1_38_11_new.dt \
     /Out /tmp/kilo/restore.log \
     /DisableStartupDialogs
   ```
   Пустой `/tmp/kilo/restore.log` означает успех. Если снова «Не найдена лицензия», проверьте, что клиент запущен от `igorvolk`, а `.lic` лежит в конфигурации этого пользователя.

Если есть готовый файл `.lic`, установите его через **«Сервис» → «Установка лицензии» → «Установить с диска»** и выберите файл. Копирование вручную в `~/.1cv8/1C/1cv8/conf/` тоже работает, но требует перезапуска клиента.

Типовые проблемы:

- **Нет кнопки «Получить лицензию»** — платформа старше 8.3.23, запущен серверный бинарник `1cv8s` вместо клиента `1cv8` или нет графической сессии.
- **Неверный логин/пароль** — нужны данные `developer.1c.ru`, а не `portal.1c.ru`, `its.1c.ru` или EDT Start.
- **Лицензия не найдена после установки** — клиент запущен от другого пользователя или под `sudo`; лицензия ищется в домашнем каталоге пользователя.
- **Исчерпан лимит активаций** — в личном кабинете разработчика можно отвязать старые компьютеры; на одного разработчика допускается несколько активаций, но не более установленного лимита.
- **Лицензия не подходит для production** — community-лицензия предназначена только для разработки; для эксплуатации нужна коммерческая лицензия.

### 12.2. Восстановление, импорт и сборка

Фактическая база: `ДокументооборотПРОФ`, версия 2.1.38.11, режим совместимости 8.3.27. Пользователь демо-базы `Администратор` без пароля.

Восстановление:

```bash
/opt/1cv8/x86_64/8.3.27.2342/1cv8 DESIGNER \
  /F/home/igorvolk/1C/ai_scrivener_docmng \
  /N Администратор \
  /RestoreIB /tmp/kilo/docmng/DocMng_2_1_38_11_new.dt \
  /Out /tmp/kilo/restore.log \
  /DisableStartupDialogs
```

После первого запуска восстановленной базы 1С показывает диалог «Информационная база была перемещена или восстановлена из резервной копии». Выберите **«Восстановлена из резервной копии»** и нажмите **«ОК»/«Продолжить»**. Пока диалог открыт, запуск клиента выглядит зависшим.

Серверный вариант PostgreSQL описан в `docs/postgresql.md`: используется образ `kustoff/1c-postgres` с расширением `mchar`, база `ai_scrivener`, подключение `/Slocalhost:1541/ai_scrivener`. Файловая база при этом остаётся рабочим резервным стендом.

Выгрузка конфигурации в XML для EDT:

```bash
/opt/1cv8/x86_64/8.3.27.2342/1cv8 DESIGNER \
  /F/home/igorvolk/1C/ai_scrivener_docmng \
  /N Администратор \
  /DumpConfigToFiles /tmp/kilo/docmng_xml \
  /Out /tmp/kilo/dump.log \
  /DisableStartupDialogs
```

Импорт базовой конфигурации в EDT:

```bash
"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/docmng_base \
  -timeout 1700 -vmargs -Xmx8g \
  -command import --version 8.3.27 \
  --configuration-files /tmp/kilo/docmng_xml \
  --project-name DocMng_2_1_38_11 --build false
```

Импорт расширения в EDT (в чистой рабочей области, где проект `ai_scrivener` ещё не создан):

```bash
"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/docmng_base \
  -timeout 550 -vmargs -Xmx4g \
  -command import --version 8.3.27 \
  --base-project-name DocMng_2_1_38_11 \
  --configuration-files /home/igorvolk/PycharmProjects/ai_scrivener/scripts/setup/ai_scrivener_ext \
  --project-name ai_scrivener --build false
```

Сборка и проверка (имя проекта — то, которое зарегистрировано в рабочей области EDT):

```bash
"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/docmng_base \
  -timeout 850 -vmargs -Xmx8g \
  -command build -y true "ai_scrivener"

"/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt/1cedtcli" \
  -data /home/igorvolk/.edt-workspace/docmng_base \
  -timeout 850 -vmargs -Xmx8g \
  -command validate --file /tmp/kilo/validate_ext.tsv \
  --project-name-list "ai_scrivener"
```

Пустой TSV-отчёт означает отсутствие ошибок. В репозитории `src/` хранятся исходники расширения; `DT-INF/PROJECT.PMF` содержит `Base-Project: DocMng_2_1_38_11`. Проект базовой конфигурации, `.dt`, `.cf` и `.cfe` в Git не коммитятся.

## 13. Контроль версий

Источник истины — `src/` в Git, а не Конфигуратор. Рабочая база — тестовая среда.

```bash
./scripts/build/export_extension.sh      # src → EDT-копия → artifacts/extension-xml
./scripts/build/load_extension.sh server # XML → серверная база
./scripts/build/dump_extension.sh server # расширение из базы → artifacts/base-extension-xml
```

Проверки:

- `make check` — общие проверки, тесты, манифест расширения;
- хук `forbid-1c-binaries` не даёт закоммитить `.cfe`, `.cf`, `.dt`, `.1CD`;
- `.gitattributes` фиксирует LF для текста и binary для артефактов 1С.

Полные правила, checksum базы и релизный цикл — в `docs/versioning.md`.
