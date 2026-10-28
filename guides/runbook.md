# Руководство по запуску

Практическое руководство: как самому запустить платформу, базу, Конфигуратор, EDT, расширение и RAG-сервис.

## 0. Что где лежит

| Компонент | Путь или значение |
|---|---|
| Платформа 1С | `/opt/1cv8/x86_64/8.3.27.2342/1cv8` |
| Толстый клиент и Конфигуратор | `/opt/1cv8/x86_64/8.3.27.2342/1cv8` |
| Тонкий клиент | `/opt/1cv8/x86_64/8.3.27.2342/1cv8c` |
| Файловая база | `/home/igorvolk/1C/ai_scrivener_docmng` |
| Выгрузка базы | `/home/igorvolk/Загрузки/DocMng_2_1_38_11_new.zip` → `DocMng_2_1_38_11_new.dt` |
| Базовая конфигурация | `ДокументооборотПРОФ`, 2.1.38.11, режим совместимости 8.3.27 |
| Пользователь базы | `Администратор`, пароль пустой |
| EDT | `/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt` |
| Java для EDT | `/opt/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/java` |
| Рабочая область EDT | `/home/igorvolk/.edt-workspace/docmng_base` |
| Проект базы в EDT | `DocMng_2_1_38_11` |
| Проект расширения в EDT | `ai_scrivener_build` (рабочая копия) |
| Исходники расширения | `/home/igorvolk/PycharmProjects/ai_scrivener/src` |
| RAG-сервис | `http://127.0.0.1:8080` |
| Qdrant | внутри Docker Compose, наружу не публикуется |

Откройте терминал и задайте переменные, чтобы команды были короче:

```bash
export ONEC=/opt/1cv8/x86_64/8.3.27.2342/1cv8
export IB=/home/igorvolk/1C/ai_scrivener_docmng
export EDT_HOME="/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt"
export EDT_JAVA=/opt/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/java
export EDT_DATA=/home/igorvolk/.edt-workspace/docmng_base
export PROJ=/home/igorvolk/PycharmProjects/ai_scrivener
```

Переменные действуют только в текущем терминале. Для нового терминала повторите `export`.

## 1. Проверка лицензии

Запустите клиент:

```bash
"$ONEC"
```

Если окно запуска открылось без сообщения о лицензии — всё готово. Если появилось «Не найдена лицензия», активируйте community-лицензию по разделу `12.1` в `guides/development.md`.

Клиент запускайте от пользователя `igorvolk`, без `sudo`. Лицензия ищется в домашнем каталоге пользователя.

## 2. Окно запуска 1С

```bash
"$ONEC"
```

Откроется окно «1С:Предприятие» со списком информационных баз.

Обёртка для запуска (используйте `bash`, не `sh`):

```bash
bash scripts/run/1c.sh            # окно запуска
bash scripts/run/1c.sh designer   # Конфигуратор
bash scripts/run/1c.sh enterprise # 1С:Предприятие
bash scripts/run/1c.sh check      # CheckConfig
```

### 2.1. Добавить существующую базу

1. Нажмите **«Добавить»**.
2. Выберите **«Добавление существующей информационной базы»**.
3. Нажмите **«Далее»**.
4. Укажите имя, например `DocMng PROF 2.1.38.11`.
5. Выберите **«В файл»** и укажите каталог `/home/igorvolk/1C/ai_scrivener_docmng`.
6. Нажмите **«Далее»** и **«Готово»**.

В списке появится база. При первом запуске введите пользователя `Администратор`, пароль оставьте пустым.

### 2.2. Запустить Конфигуратор

Выберите базу в списке и нажмите **«Конфигуратор»**. Или одной командой:

```bash
"$ONEC" DESIGNER /F"$IB" /N Администратор
```

### 2.3. Запустить 1С:Предприятие

Выберите базу и нажмите **«1С:Предприятие»**. Или одной командой:

```bash
"$ONEC" ENTERPRISE /F"$IB" /N Администратор
```

Пользователь — `Администратор`, пароль пустой. Если пароль всё же запрашивается, оставьте поле пустым.

### 2.4. Серверная база PostgreSQL

Проще всего одной командой, которая поднимает PostgreSQL и кластер 1С:

```bash
./scripts/run/1c-pg-server.sh
```

Терминал оставьте открытым. Остановка — `Ctrl+C` или:

```bash
./scripts/run/1c-pg-server.sh stop
```

Если агент 1С уже запущен, скрипт не поднимает второй и сообщает об этом. Остановите старый командой `stop` и запустите снова.

Или раздельно: PostgreSQL через Compose, кластер 1С — командой `ragent`.

### 2.5. Веб-клиент через автономный сервер (для Playwright)

Толстый/тонкий клиент — десктопное приложение, им нельзя управлять программно (нет `xdotool`/инструмента ввода). Автономный сервер `ibsrv` поднимает ту же базу с веб-клиентом на чистом HTML/JS без Apache — его может водить Playwright: заходить под разными демо-пользователями, кликать, читать DOM — без участия человека.

```bash
mkdir -p /tmp/kilo/standalone-server
/opt/1cv8/x86_64/8.3.27.2342/ibcmd server config init \
  -o /tmp/kilo/standalone-server/server.json \
  --http-address=localhost --http-port=8314 --http-base=/ai_scrivener \
  --database-path="$IB" --name=ai_scrivener

/opt/1cv8/x86_64/8.3.27.2342/ibsrv \
  --config=/tmp/kilo/standalone-server/server.json \
  --data=/tmp/kilo/standalone-server/data &
```

База доступна на `http://localhost:8314/ai_scrivener/`. Проверка:

```bash
curl -sI http://localhost:8314/ai_scrivener/
```

### 2.6. `HTTPService` расширения через Apache (для программного доступа извне)

`HTTPService.АИС_Симулятор` — тестовый адаптер для симулятора предприятия. В штатной работе без симулятора он не используется: документы создаются штатными средствами 1С:Документооборота, а расширение обрабатывает их подписками и AI-контуром.

`ibsrv` (§2.5) хорош для веб-клиента, но в этой версии платформы (8.3.27.2342) `HTTPService`-вызовы через него падают с внутренней ошибкой `sessionId != kUUIDNull` — похоже, это ограничение/баг именно автономного сервера, не нашего кода (проверено: роутинг резолвится, аутентификация не при чём, не зависит от метода/cookie). Для `HTTPService` нужна классическая публикация через Apache + модуль 1С.

**Установка (один раз):**

1. Компонент `ws` (веб-коннектор Apache/nginx) не входит в базовую установку — ставится отдельно из полного дистрибутива сервера (`server64_*.zip` → `setup-full-*.run`):
   ```bash
   sudo /путь/к/setup-full-8.3.27.2342-x86_64.run --mode unattended --enable-components ws
   ```
   Это кладёт `wsap24.so`/`wsap22.so`/`wsapch2.so` в каталог платформы. Сам Apache ставится отдельно: `sudo apt-get install -y apache2`.
2. Публикация через штатную утилиту `webinst`:
   ```bash
   sudo mkdir -p /var/www/ai_scrivener
   sudo chown igorvolk:igorvolk /var/www/ai_scrivener
   sudo "$ONEC_DIR/webinst" -publish -apache24 -wsdir ai_scrivener -dir /var/www/ai_scrivener \
     -connstr 'File="/home/igorvolk/1C/ai_scrivener_docmng";' -confPath /etc/apache2/apache2.conf
   sudo systemctl restart apache2
   ```
   Это добавляет `LoadModule`+`Alias`+`<Directory>` в `apache2.conf` и создаёт `/var/www/ai_scrivener/default.vrd`.
3. **`webinst` не включает `HTTPService` в `default.vrd`** — там только `<ws>` (SOAP) и `<standardOdata>`. Нужно дописать вручную, и это не плоский флаг, а список сервисов по имени (`rootURL` расширения):
   ```xml
   <httpServices>
       <service name="ais-sim" rootUrl="ais-sim" enable="true"
               reuseSessions="autouse" sessionMaxAge="20" poolSize="10" poolTimeout="5"/>
   </httpServices>
   ```
   (вставить рядом с `<ws .../>`; `<httpServices enable="true"/>` одним флагом — невалидно, платформа бросает `Error converting XDTO data: PropertyStart: enable`).
4. Мастер **Администрирование → Публикация на веб-сервере** в Конфигураторе делает то же самое из коробки (и корректно формирует `httpServices`), но требует суперпользователя (пишет в `/etc/apache2/apache2.conf`) — а лицензия community-версии видна только пользователю `igorvolk`, не `root`, так что запустить Конфигуратор от root для этого не выйдет без лишних манипуляций с лицензией. Проще править `default.vrd` руками по образцу выше.

**Проверка:**
```bash
curl -s -u "Администратор:" -X POST -H "Content-Type: application/json; charset=utf-8" \
  --data-raw '{"Имя":"Тест","ФИО":"...","Должность":"...","Роли":["ДолжностноеЛицо"]}' \
  http://localhost/ai_scrivener/hs/ais-sim/employees -i
```

**Повторяющаяся проблема: конфликт прав `igorvolk` vs `www-data`.** Apache-воркер (`www-data`) и Конфигуратор/`1cv8` (`igorvolk`) обращаются к одним файлам файловой базы (`1Cv8.1CD`, `*.1CL`, временные `1Cv8tmp.*`). Каждая сторона создаёт файлы под своим пользователем без прав для другого — следующая попытка открыть базу из другого аккаунта падает с «Ошибка режима доступа»/«Ошибка открытия файла блокировок». Рабочий паттерн:
- **Перед** открытием Конфигуратора после любого HTTP-запроса: `sudo systemctl stop apache2`, затем `chmod -R o+rw` на каталог базы (не страшно, если часть файлов вроде `1CHelpIndex`/`1Cv8Temp` откажет — они не нужны ни той, ни другой стороне в этом сценарии), удалить `1Cv8tmp.*`/`*.1CL`, если chmod на них не прошёл (`rm -f`, т.к. право на удаление даёт запись в каталог, а не владение файлом).
- **После** Конфигуратора: `sudo systemctl start apache2`.
- При смене кода (`load_extension.sh file`) та же база нужна и Конфигуратору — Apache тоже должен быть остановлен на это время.

Для реальной эксплуатации (не разработки) это не проблема — там один владелец процесса публикации; конфликт специфичен именно для dev-окружения, где одна и та же файловая база используется и интерактивно, и через веб-публикацию.

Playwright (headless Chromium, отдельный venv, чтобы не трогать `uv`-окружение проекта):

```bash
python3 -m venv /tmp/kilo/pw-venv
/tmp/kilo/pw-venv/bin/pip install --quiet playwright
/tmp/kilo/pw-venv/bin/playwright install chromium
```

Логин (поле пользователя — первый `input` на странице, пароль у демо-пользователей пустой, кнопка `#authWindow_basic_okButton`):

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("http://localhost:8314/ai_scrivener/")
    page.wait_for_timeout(2000)
    page.locator("input").nth(0).fill("ДЛ1")
    page.locator("#authWindow_basic_okButton").click()
    page.wait_for_timeout(6000)
    page.screenshot(path="/tmp/kilo/web.png")
    browser.close()
```

Это рабочий интерфейс один в один с толстым клиентом (те же формы, списки, поиск Ctrl+Shift+F) — проверено на демо-пользователях B5 (вход, поиск задач, просмотр форм). Остановка сервера — `kill` по PID из `pgrep -af ibsrv`.

Запуск клиента:

```bash
./scripts/run/1c.sh pg-enterprise
./scripts/run/1c.sh pg-designer
./scripts/run/1c.sh pg-check
./scripts/run/1c.sh pg-db
```

Строка подключения: `/Slocalhost:1541/ai_scrivener`, пользователь `Администратор`, пароль пустой. Подробности — в `guides/postgresql.md`.

### 2.7. Симулятор предприятия (LLM-агенты)

Симулятор живёт в отдельном репозитории `ai-scrivener-enterprise-sim` и ходит в расширение только через `HTTPService.АИС_Симулятор` (§2.6). Он не требует доступа к исходникам или базе `ai_scrivener`; каждый вызов аутентифицируется как реальный пользователь 1С.

```bash
cd ~/PycharmProjects/ai-scrivener-enterprise-sim
uv sync
```

Переменные окружения: `AIS_SIM_BASE_URL` (по умолчанию `http://localhost/ai_scrivener`), `AIS_SIM_AUTH_LOGIN` (логин сотрудника, от имени которого действует агент), `AIS_SIM_AUTH_PASSWORD`, `AIS_SIM_COMPANY_PROFILE` (профиль компании), `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`.

```bash
AIS_SIM_AUTH_LOGIN=Администратор uv run python -m enterprise_sim.seed
AIS_SIM_AUTH_LOGIN=Администратор uv run python -m enterprise_sim.seed_owner
AIS_SIM_AUTH_LOGIN=Администратор uv run python -m enterprise_sim.seed_programmer
AIS_SIM_AUTH_LOGIN=ДиректорПоПерсоналу uv run python -m enterprise_sim.hire_management
AIS_SIM_AUTH_LOGIN=ДиректорПоПерсоналу uv run python -m enterprise_sim.hire_engineering
uv run python -m enterprise_sim.issue_founding_orders
AIS_SIM_AUTH_LOGIN=ГлавныйИнженер uv run python -m enterprise_sim.deepseek_agent "Главный инженер"
```

Перед запуском убедиться, что Apache опубликован (§2.6) и база не занята Конфигуратором/EDT. `issue_founding_orders` не идемпотентен: повторный запуск создаёт новые документы и задачи. Полный сценарий, профиль компании и текущие ограничения — `plans/2026-10-26-enterprise-simulator.md` и README симулятора.

## 3. Расширение в Конфигураторе

### 3.1. Создать расширение

1. В Конфигураторе откройте **«Конфигурация» → «Расширения конфигурации»**.
2. Нажмите **«Добавить»**.
3. Укажите:
   - **Имя:** `ai_scrivener`
   - **Синоним:** `AI Scrivener`
   - **Префикс:** `АИС_`
   - **Режим совместимости:** `8.3.27`
4. Нажмите **«ОК»**.
5. Сохраните конфигурацию: `Ctrl+S`.

Расширение хранится в самой базе, а не отдельным файлом.

### 3.2. Открыть расширение

В окне «Расширения конфигурации» дважды щёлкните по `ai_scrivener` или выберите **«Открыть конфигурацию расширения»**. Откроется отдельное дерево метаданных расширения.

### 3.3. Загрузить объекты из XML

Если объекты уже подготовлены в EDT и выгружены в XML:

```bash
"$ONEC" DESIGNER /F"$IB" /N Администратор \
  /LoadConfigFromFiles /tmp/kilo/ai_scrivener_export \
  -Extension ai_scrivener \
  -updateConfigDumpInfo \
  /UpdateDBCfg \
  /Out /tmp/kilo/load_ext.log \
  /DisableStartupDialogs
```

Проверьте лог:

```bash
cat /tmp/kilo/load_ext.log
```

Пустой лог — успех. Если команда пишет «Загрузка не должна менять принадлежность основного объекта конфигурации», значит расширение `ai_scrivener` ещё не создано в базе. Сначала выполните шаг 3.1.

### 3.4. Сохранить расширение в `.cfe`

1. В окне **«Расширения конфигурации»** выберите `ai_scrivener`.
2. Откройте **«Конфигурация» → «Сохранить конфигурацию в файл»**.
3. Укажите путь, например `/home/igorvolk/1C/ai_scrivener.cfe`.
4. Сохраните.

### 3.5. Применить `.cfe`

1. В Конфигураторе откройте **«Конфигурация» → «Расширения конфигурации»**.
2. Нажмите **«Загрузить расширение из файла»**.
3. Выберите `/home/igorvolk/1C/ai_scrivener.cfe`.
4. Убедитесь, что стоит флажок **«Активно»**.
5. Нажмите **«ОК»** и сохраните: `Ctrl+S`.
6. Обновите конфигурацию БД: `F7` (или **«Конфигурация» → «Обновить конфигурацию БД»**).

Проверка применимости: **«Конфигурация» → «Проверка возможности применения»**.

## 4. Запуск EDT

```bash
"$EDT_HOME/1cedt" -vm "$EDT_JAVA" -data "$EDT_DATA"
```

Откроется Eclipse/EDT с рабочей областью `docmng_base`.

В ней уже есть:

- `DocMng_2_1_38_11` — импортированная базовая конфигурация;
- `ai_scrivener_build` — рабочая копия расширения, на которой проверяются сборки;
- проект `ai_scrivener` из репозитория может быть не открыт.

### 4.1. Открыть проект из репозитория

1. **File → Import**.
2. **General → Existing Projects into Workspace**.
3. **Select root directory** → `/home/igorvolk/PycharmProjects/ai_scrivener`.
4. **Finish**.

Проект `ai_scrivener` привязан к базе через `DT-INF/PROJECT.PMF` (`Base-Project: DocMng_2_1_38_11`).

### 4.2. Сборка и проверка в EDT

- Сборка: **Project → Build Project** (или `Ctrl+B`).
- Проверка: правой кнопкой по проекту → **Validate**.
- Если EDT пишет, что пространство имён базы неактивно, сначала соберите `DocMng_2_1_38_11`, затем расширение.

### 4.3. Сборка и проверка через CLI

```bash
"$EDT_HOME/1cedtcli" -data "$EDT_DATA" -timeout 850 -vmargs -Xmx8g \
  -command build -y true "ai_scrivener_build"

"$EDT_HOME/1cedtcli" -data "$EDT_DATA" -timeout 850 -vmargs -Xmx8g \
  -command validate --file /tmp/kilo/validate_ext.tsv \
  --project-name-list "ai_scrivener_build"

cat /tmp/kilo/validate_ext.tsv
```

Пустой TSV — ошибок нет. Предупреждения о неизвестных типах базовых объектов в CLI-проверке допустимы, если сборка проходит; в GUI при открытой базе они не появляются.

### 4.4. Выгрузить расширение в XML

```bash
"$EDT_HOME/1cedtcli" -data "$EDT_DATA" -timeout 550 -vmargs -Xmx8g \
  -command export --project-name "ai_scrivener_build" \
  --configuration-files /tmp/kilo/ai_scrivener_export
```

Полученный каталог загружается в базу командой из шага 3.3.

## 5. RAG-сервис

Подготовьте окружение один раз:

```bash
cp rag-service/.env.example rag-service/.env
```

Заполните `rag-service/.env`: `RAG_GIGACHAT_CLIENT_ID`, `RAG_GIGACHAT_CLIENT_SECRET`, `RAG_SERVICE_TOKEN`. Файл `.env` в Git не коммитится.

Запуск:

```bash
docker compose -f deploy/docker-compose.yml up --build -d
docker compose -f deploy/docker-compose.yml ps
curl http://127.0.0.1:8080/health
```

Логи:

```bash
docker compose -f deploy/docker-compose.yml logs -f rag-service
```

Остановка:

```bash
docker compose -f deploy/docker-compose.yml down
```

`down` сохраняет том Qdrant. `down -v` удаляет векторы — используйте только если готовы переиндексировать.

## 6. Проверки проекта

```bash
make check
uv run pytest
uv run pytest rag-service/tests
```

Проверка конфигурации 1С:

```bash
"$ONEC" DESIGNER /F"$IB" /N Администратор \
  /CheckConfig \
  /Out /tmp/kilo/check.log \
  /DisableStartupDialogs

cat /tmp/kilo/check.log
```

## 6.1. Базовые данные

1. Применить расширение к копии демо-базы.
2. Базовые должности, сотрудники и последовательность приказов собственника задаются в `config/enterprise.json` и редактируются в UI симулятора (`uv run python -m enterprise_sim.ui`).
3. Симулятор создаёт базовый набор скриптом `seed_config` или кнопкой «Заполнить базовые данные» в UI. Повторный запуск идемпотентен.
4. Начальные тексты промптов и параметры создаются обработкой **`АИС: Сервис` → «Заполнить промпты»** (`АИС_ЗаполнитьПромпты`); она не создаёт пользователей и должности.
5. Приказы собственника выполняются по одному в строгой последовательности: следующая кнопка/команда доступна после завершения предыдущего приказа.

## 6.2. Проверка UI расширения

- **«АИС: Сервис» → «Структура предприятия и подчиненность»** — дерево подразделений и дерево персональной подчиненности.
- **«АИС: Сервис» → «Шаблоны документов»** — единый список шаблонов внутренних, входящих и исходящих документов с текстом и встроенным редактированием статуса/текста.
- **«АИС: Сервис» → «Тексты промптов ИИ»** — тексты промптов; **«Параметры промптов ИИ»** — модель, температура, лимит токенов и версия.
- Редактирование шаблонов доступно `Администратор` и `Программист1С` (роль `АИС_АдминистраторСистемы`).

## 7. Полный порядок запуска

1. Проверить лицензию (раздел 1).
2. Открыть базу в Конфигураторе (раздел 2.2).
3. Создать расширение `ai_scrivener` (раздел 3.1).
4. Загрузить объекты из XML или EDT (раздел 3.3).
5. Сохранить `.cfe` и применить (разделы 3.4–3.5).
6. Запустить RAG-сервис (раздел 5).
7. Запустить 1С:Предприятие (раздел 2.3).
8. Прогнать проверки (раздел 6).
9. Для сценариев симулятора опубликовать `HTTPService` через Apache (раздел 2.6) и запустить агентов (раздел 2.7).

## 8. Типовые проблемы

| Симптом | Что сделать |
|---|---|
| «Не найдена лицензия» | Активировать community-лицензию, запускать от `igorvolk`, не через `sudo` |
| «Информационная база была перемещена или восстановлена из резервной копии» | Выбрать вариант **«Восстановлена из резервной копии»** и нажать **«ОК»/«Продолжить»**. Это разовый диалог после восстановления `.dt`; пока он открыт, запуск висит |
| «Пользователь ИБ не идентифицирован» | `/N Администратор` без `/P`; пароль пустой; не передавайте `/P ""` |
| «Загрузка не должна менять принадлежность основного объекта» | Сначала создать расширение в Конфигураторе (раздел 3.1) |
| «Пространство имён базы неактивно» | Собрать проект базы `DocMng_2_1_38_11`, затем расширение |
| «Не найден вариант вызова команды» у `build`/`validate` | Передавать один проект за вызов; список из нескольких имён CLI не принимает |
| База занята | Закрыть все окна 1С; проверить `pgrep -a 1cv8`; завершить процесс по PID |
| EDT не стартует | Запускать с `-vm "$EDT_JAVA"` |
| В меню приложений нет 1С | Запустить `$ONEC` из терминала или обновить ярлык: `update-desktop-database ~/.local/share/applications` |
| `/health` RAG не отвечает | `docker compose ps`, логи `rag-service`, проверить `.env`, CA-сертификат GigaChat |
| Нужно сбросить Qdrant | `docker compose -f deploy/docker-compose.yml down -v` (удаляет векторы) |

### 8.1. Как показать экран 1С

Модель не читает изображения, но читает OCR-текст. Скрипт захватывает окно 1С и распознаёт текст:

```bash
./scripts/debug/screenshot_ocr.sh
```

Полезные варианты:

```bash
./scripts/debug/screenshot_ocr.sh --list          # список окон и их ID
./scripts/debug/screenshot_ocr.sh --window 0x140022b
```

- скриншот сохраняется в `/tmp/kilo/1c-screen.png`;
- распознанный текст выводится в консоль;
- по умолчанию берётся первое окно `1cv8`;
- для отдельного диалога укажите его ID из `--list`.

OCR читает заголовки, поля, ошибки и пункты меню, но не понимает иконки и вёрстку. Для десктопного 1С это рабочий способ показать состояние экрана; для автоматизации кликов и форм — автономный сервер + Playwright (раздел 2.5), это даёт полноценный DOM и реальный клик вместо чтения скриншота.

## 9. Остановка

1. Закройте 1С:Предприятие, Конфигуратор и EDT.
2. Проверьте процессы 1С:

```bash
pgrep -a 1cv8
```

3. Если процесс остался, завершите его по PID:

```bash
kill <PID>
```

4. Остановите RAG-сервис:

```bash
docker compose -f deploy/docker-compose.yml down
```

## 10. Связанные документы

- `guides/development.md` — установка, лицензия, восстановление базы, импорт в EDT.
- `plans/implementation_plan.md` — архитектура расширения и маппинг объектов.
- `guides/postgresql.md` — вариант PostgreSQL для 1С, расширение `mchar` и серверный кластер.
- `guides/versioning.md` — источник истины, артефакты, пересборка базы и релизный цикл.
- `docs/data-model.md` — дедуплицированная модель данных расширения.
- `docs/process-diagrams.md` — процессы AS-IS и TO-BE.
- `docs/template-factory.md` — мастер шаблонов и автошаблонизация.
- `docs/proofreading.md` — вычитка документов и квоты LLM.
- `plans/2026-10-26-enterprise-simulator.md` — симулятор предприятия, агенты и текущие ограничения.
- `ai-scrivener-enterprise-sim/README.md` — запуск симулятора и профиль компании.
- `docs/design-decisions.md` — завершённые проектные решения.
- `docs/requirements/traceability_matrix.md` — требования и сценарии проверки.
