# PostgreSQL для 1С: рабочая инструкция

## 1. Короткий вывод

Стандартный PostgreSQL (`postgres:15`, `postgres:16`) для 1С **не подходит**: при создании серверной базы 1С требует расширение `mchar`, которого в обычном образе нет.

Рабочий вариант — специализированный образ PostgreSQL для 1С. В проекте используется:

```text
kustoff/1c-postgres:latest
PostgreSQL 12.4 (Ubuntu 12.4-1.1C)
```

В нём уже есть `mchar`, `fulleq`, `fasttrun` и локаль `ru_RU.utf8`.

## 2. Текущий статус

- Контейнер `deploy-postgres-1` запущен, PostgreSQL слушает `127.0.0.1:5432`.
- База `ai_scrivener` создана, в неё восстановлена демо-база `DocMng_2_1_38_11_new.dt`.
- В базе 1363 таблицы, размер около 173 МБ.
- Серверный кластер 1С запускается вручную (`ragent`, `rmngr`, `rphost`) и слушает `1540`/`1541`.
- Клиент подключается строкой `/Slocalhost:1541/ai_scrivener`.
- Файловая база `/home/igorvolk/1C/ai_scrivener_docmng` остаётся рабочим резервным стендом.

## 3. Запуск PostgreSQL

Проще всего одной командой — она поднимает контейнер и серверный кластер 1С в одном терминале:

```bash
./scripts/run/1c-pg-server.sh
```

Терминал должен оставаться открытым. Остановка — `Ctrl+C` или отдельной командой:

```bash
./scripts/run/1c-pg-server.sh stop
```

`stop` завершает агент 1С и останавливает контейнер PostgreSQL. Если агент уже запущен, скрипт не запускает второй, а сообщает об этом и предлагает использовать `./scripts/run/1c.sh pg-enterprise`.

Раздельно:

```bash
docker compose -f deploy/docker-compose.1c-db.yml up -d
docker compose -f deploy/docker-compose.1c-db.yml ps
```

Проверка:

```bash
docker exec deploy-postgres-1 psql -U ai_scrivener -d postgres -c "\l"
docker exec deploy-postgres-1 psql -U ai_scrivener -d ai_scrivener -c "\dx"
```

В списке расширений должны быть:

```text
mchar
fulleq
fasttrun
plpgsql
```

Если контейнер пересоздавался с пустым томом, базу `ai_scrivener` нужно создать заново и восстановить `.dt` (разделы 5–6).

## 4. Запуск серверного кластера 1С

Серверные компоненты установлены. Для учебного стенда кластер можно запускать от текущего пользователя, без systemd:

```bash
mkdir -p /home/igorvolk/1C/1cv8-server-data

/opt/1cv8/x86_64/8.3.27.2342/ragent \
  -d /home/igorvolk/1C/1cv8-server-data \
  -port 1540 -regport 1541 -range 1560:1591 -seclev 0
```

Проверка:

```bash
ss -ltnp
```

Должны быть заняты `1540` и `1541`.

Остановка:

```bash
pkill -f ragent
```

Или завершите процесс `ragent` по PID.

## 5. Создание серверной базы

```bash
/opt/1cv8/x86_64/8.3.27.2342/1cv8 CREATEINFOBASE \
  'Srvr=localhost:1541;Ref=ai_scrivener;DBMS=PostgreSQL;DBSrvr=127.0.0.1;DB=ai_scrivener;DBUID=ai_scrivener;DBPwd=ai_scrivener_dev;Locale=ru;CrSQLDB=Y;LicDstr=Y' \
  /N Администратор \
  /Out /tmp/kilo/create_ib.log \
  /DisableStartupDialogs

cat /tmp/kilo/create_ib.log
```

Ключи важны: `DBSrvr`, `DB`, `DBUID`, `DBPwd`. Вариант с `DBServer`, `DBName`, `DBUser` 1С не принимает.

Успешный лог:

```text
Создание информационной базы (...) успешно завершено
```

## 6. Восстановление демо-базы в PostgreSQL

Для **пустой** серверной базы восстановление выполняется **без** `/N`:

```bash
/opt/1cv8/x86_64/8.3.27.2342/1cv8 DESIGNER \
  /Slocalhost:1541/ai_scrivener \
  /RestoreIB /tmp/kilo/docmng/DocMng_2_1_38_11_new.dt \
  /Out /tmp/kilo/restore_pg.log \
  /DisableStartupDialogs

cat /tmp/kilo/restore_pg.log
```

Успешный лог:

```text
Загрузка информационной базы успешно завершена
```

Если передать `/N Администратор` до восстановления, будет ошибка `Пользователь ИБ не идентифицирован`: в пустой базе ещё нет пользователей.

## 7. Подключение клиента

```bash
/opt/1cv8/x86_64/8.3.27.2342/1cv8 ENTERPRISE \
  /Slocalhost:1541/ai_scrivener /N Администратор
```

Или через скрипт:

```bash
./scripts/run/1c.sh pg-enterprise
./scripts/run/1c.sh pg-designer
./scripts/run/1c.sh pg-check
```

В окне запуска можно добавить базу:

- **«Добавить» → «Добавление существующей информационной базы»**;
- **«На сервере 1С:Предприятия»**;
- сервер: `localhost:1541`;
- имя базы: `ai_scrivener`;
- пользователь: `Администратор`, пароль пустой.

## 8. Как смотреть базу

Интерактивный `psql`:

```bash
./scripts/run/1c.sh pg-db
```

Или:

```bash
docker exec -it deploy-postgres-1 psql -U ai_scrivener -d ai_scrivener
```

Полезные команды:

```sql
\dt
\dt _reference*
\dt _document*
\dt _inforg*
\d v8users
select name, descr, show, admrole from v8users;
select count(*) from "_reference123";
select * from "_reference123" limit 10;
```

Пользователи базы видны в `v8users`:

```sql
select name, descr, show, admrole from v8users;
```

Таблицы 1С имеют служебные имена:

- `_reference...` — справочники;
- `_document...` — документы;
- `_inforg...` — регистры сведений;
- `_accumrg...` — регистры накопления;
- `_enum...` — перечисления;
- `_vt...` — табличные части;
- `_fld...` — поля.

Это внутреннее представление платформы, а не удобная прикладная схема. Числовые суффиксы таблиц не совпадают с именами объектов метаданных, поэтому искать нужную таблицу лучше через Конфигуратор или по составу полей.

## 9. Ограничения

- Стандартный PostgreSQL не подходит без `mchar`.
- Для серверной базы нужен серверный компонент 1С и, возможно, отдельная серверная лицензия.
- PostgreSQL 12.4-1.1C — специализированная сборка; не обновляйте её обычными средствами PostgreSQL.
- Файловая база проще для разработки расширения; PostgreSQL удобнее для просмотра SQL-схемы и production.
- Расширение и его код не зависят от типа СУБД.
