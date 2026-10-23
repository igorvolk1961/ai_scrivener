# C4-модель ai_scrivener

Целевая архитектура (TO-BE) на 2026-10-23. Диаграммы показывают проектное устройство системы; фактическое состояние кода отражено в таблицах статусов. Сейчас реализованы RAG-сервис и часть метаданных расширения, компоненты бизнес-логики на BSL ещё не созданы.

Нотация — [C4 model](https://c4model.com/): контекст, контейнеры, компоненты. Диаграммы отрисованы в Mermaid flowchart: уровни C4 сохранены как семантические границы, а flowchart даёт более устойчивое чтение и рендеринг, чем экспериментальный C4-синтаксис. Пунктирная связь означает опциональную или отложенную интеграцию.

## 1. Контекст

Кто пользуется системой и с какими внешними системами она взаимодействует.

```mermaid
flowchart LR
    subgraph Actors["Пользователи"]
        DL["Должностное лицо"]
        SUP["Вышестоящее ДЛ"]
        ADM["Администратор системы"]
        AUD["Аудитор"]
        MET["Методолог"]
        CLERK["Делопроизводитель"]
    end

    AIS["AI Scrivener<br/>расширение 1С + RAG-сервис"]

    subgraph External["Внешние системы"]
        DOC["1С:Документооборот 2.1.38.11<br/>документы, задачи, права"]
        DS["DeepSeek API<br/>генерация и классификация"]
        GC["GigaChat API<br/>эмбеддинги"]
        QD["Qdrant<br/>векторный индекс"]
        LLM["Локальная LLM<br/>опционально"]
        SRC["Внешние источники<br/>API и расчёты"]
    end

    DL -->|"задачи и проекты"| AIS
    SUP -->|"доклады и подтверждение"| AIS
    ADM -->|"настройка и диагностика"| AIS
    AUD -->|"просмотр аудита"| AIS
    MET -->|"ведение шаблонов"| AIS
    CLERK -->|"регистрация документов"| DOC
    AIS -->|"читает и создаёт"| DOC
    AIS -->|"промпты и JSON"| DS
    AIS -->|"эмбеддинги"| GC
    AIS -->|"индексация и поиск"| QD
    AIS -.->|"вычитка"| LLM
    AIS -->|"значения плейсхолдеров"| SRC

    classDef actor fill:#E3F2FD,stroke:#1565C0,color:#0D47A1
    classDef sys fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#BF360C
    classDef external fill:#ECEFF1,stroke:#546E7A,color:#263238
    class DL,SUP,ADM,AUD,MET,CLERK actor
    class AIS sys
    class DOC,DS,GC,QD,LLM,SRC external
```

| Элемент | Роль | Граница |
|---|---|---|
| Должностное лицо | Основной пользователь: задачи, проекты документов, ответы на запросы | Внутри организации |
| Вышестоящее ДЛ | Получатель докладов и адресат эскалации | Внутри организации |
| Администратор системы | Настройка объектов расширения, промптов, квот, диагностика | Внутри организации |
| Аудитор | Просмотр `АИС_ИсторияДействийИИ` и отчётов без записи | Внутри организации |
| Методолог | Мастер шаблонов, проверка и утверждение версий | Внутри организации |
| Делопроизводитель | Регистрация документов в штатном Документообороте | Вне RBAC расширения |
| AI Scrivener | Расширение `.cfe` и RAG-сервис как единая система в границах проекта | В границах проекта |
| 1С:Документооборот | Источник истины доменных данных; расширение его не заменяет | Внешняя система |
| DeepSeek API | Внешняя LLM для структурированных ответов и генерации текста | Внешний сервис |
| GigaChat API | Эмбеддинги для индексации и поиска | Внешний сервис |
| Qdrant | Векторное хранилище; доступ только через RAG-сервис | Внешний сервис |
| Локальная LLM | Опциональный провайдер для конфиденциальной вычитки | Инфраструктура организации |
| Внешние источники | API и расчётные сервисы для значений плейсхолдеров | Внешние системы |

## 2. Контейнеры

Как система разделена на исполняемые единицы и хранилища.

```mermaid
flowchart LR
    subgraph Actors["Пользователи"]
        DL["Должностное лицо"]
        SUP["Вышестоящее ДЛ"]
        ADM["Администратор"]
        AUD["Аудитор"]
        MET["Методолог"]
        CLERK["Делопроизводитель"]
    end

    subgraph AIS["AI Scrivener"]
        EXTN["Расширение ai_scrivener<br/>1С:Предприятие, BSL"]
        API["RAG API<br/>Python 3.12, FastAPI"]
        QD[("Qdrant<br/>векторная БД")]
    end

    subgraph DOCS["1С:Документооборот (внешняя система)"]
        BASE["Базовая конфигурация<br/>BSL"]
        FILES[("Тома хранения файлов<br/>файлы и версии")]
    end

    PG[("PostgreSQL<br/>+ mchar")]
    PROXY["Reverse proxy / TLS"]

    subgraph External["Внешние сервисы"]
        DS["DeepSeek API"]
        GC["GigaChat API"]
        LLM["Локальная LLM"]
        SRC["Внешние источники"]
    end

    DL -->|"тонкий клиент"| EXTN
    SUP -->|"тонкий клиент"| EXTN
    ADM -->|"тонкий клиент"| EXTN
    AUD -->|"тонкий клиент"| EXTN
    MET -->|"тонкий клиент"| EXTN
    CLERK -->|"регистрация"| BASE
    EXTN -->|"читает и создаёт"| BASE
    BASE -->|"SQL"| PG
    EXTN -->|"SQL"| PG
    EXTN -->|"файлы и версии"| FILES
    EXTN -->|"HTTPS + X-Service-Token"| PROXY
    PROXY -->|"HTTP"| API
    API -->|"векторы"| QD
    API -->|"OAuth / embeddings"| GC
    EXTN -->|"промпты"| DS
    EXTN -.->|"вычитка"| LLM
    EXTN -->|"значения"| SRC

    classDef actor fill:#E3F2FD,stroke:#1565C0,color:#0D47A1
    classDef cont fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#BF360C
    classDef storage fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20
    classDef external fill:#ECEFF1,stroke:#546E7A,color:#263238
    class DL,SUP,ADM,AUD,MET,CLERK actor
    class EXTN,API,BASE cont
    class QD,PG,FILES storage
    class PROXY,DS,GC,LLM,SRC external
```

| Контейнер | Технология | Ответственность | Статус |
|---|---|---|---|
| Базовая конфигурация | 1С:Предприятие 8.3.27, BSL | Пользователи, должности, документы, задачи, бизнес-процессы, штатные права | Работает |
| Расширение `ai_scrivener` | 1С:Предприятие 8.3.27, BSL | ИИ-оркестрация, плейсхолдеры, лист ожидания, аудит, мастер шаблонов, вычитка | Метаданные частично, BSL-логики нет |
| PostgreSQL | PostgreSQL + `mchar` | Единое хранилище данных базовой конфигурации и расширения | Работает |
| Тома хранения файлов | Файловая система 1С | Файлы, версии, тома хранения | Работает |
| RAG API | Python 3.12, FastAPI, httpx, qdrant-client | `/health`, `/v1/search`, `/v1/index/upsert`, `/v1/index/replace`, `DELETE /v1/index/...` | Реализован |
| Qdrant | Векторная БД | Коллекция `ai_scrivener_knowledge_v1`, cosine, payload-индексы | Реализован в сервисе |
| Reverse proxy / TLS | nginx или аналог | Точка входа RAG API, TLS, ограничение доступа | Проект |
| DeepSeek API | Внешний OpenAI-совместимый API | Выбор шаблона, классификация, генерация, анализ срыва | Проект интеграции |
| GigaChat API | Внешний API | OAuth, `EmbeddingsGigaR`, размерность 2560 | Реализован клиент |
| Локальная LLM | OpenAI-совместимый endpoint | Глубокая вычитка конфиденциальных документов | Проект |
| Внешние источники | HTTP API, расчётные сервисы, утверждённые запросы | Значения плейсхолдеров | Проект |

## 3. Компоненты расширения

Ключевые модули, обработки и регламентные задания внутри контейнера `Расширение ai_scrivener`.

```mermaid
flowchart LR
    subgraph UI["Интерфейс"]
        UI_DL["Рабочее место ДЛ<br/>форма задачи, проект документа"]
        UI_ADM["Админ-панель"]
        UI_REM["Панель замечаний"]
    end

    subgraph CORE["Ядро оркестрации"]
        ORCH["АИС_ОркестраторЗадач"]
        RES["АИС_РазрешительПлейсхолдеров"]
        GEN["АИС_ГенераторДокументов"]
        WAIT["АИС_РаботаСЛистомОжидания"]
        AUD["АИС_АудитДействийИИ"]
        SESS["УстановкаПараметровСеанса"]
    end

    subgraph INTEGR["Интеграции"]
        QUEUE["АИС_ОчередьЗапросовLLM"]
        LLM["АИС_ИнтеграцияСLLM"]
        RAG["АИС_ИнтеграцияСRAG"]
    end

    subgraph TPL["Шаблоны"]
        TPL_M["АИС_МастерШаблонов"]
        TPL_R["АИС_ГенераторПравилШаблона"]
        TPL_C["АИС_ПроверкаШаблона"]
        TPL_S["АИС_СравнениеШаблонов"]
    end

    subgraph PROOF["Вычитка"]
        PROOF_C["АИС_ПроверкаДокумента"]
    end

    subgraph JOBS["Регламентные задания"]
        J_ORCH["Оркестрация активных задач"]
        J_IDX["Индексация RAG"]
        J_WAIT["Обработка листа ожидания"]
        J_DEAD["Проверка сроков"]
        J_TIMER["Генерация триггеров"]
    end

    BASE["Базовая конфигурация"]
    API["RAG API"]
    DS["DeepSeek API"]
    LLM_EXT["Локальная LLM"]
    SRC["Внешние источники"]

    UI_DL --> ORCH
    UI_DL --> TPL_M
    UI_REM --> PROOF_C
    UI_ADM --> TPL_M
    UI_ADM --> API
    SESS --> ORCH
    ORCH --> RES
    ORCH --> GEN
    ORCH --> WAIT
    ORCH --> AUD
    RES --> RAG
    RES --> LLM
    RES --> WAIT
    RES --> SRC
    GEN --> LLM
    GEN --> BASE
    WAIT --> BASE
    ORCH --> BASE
    TPL_M --> TPL_R
    TPL_M --> TPL_C
    TPL_M --> TPL_S
    TPL_M --> RAG
    PROOF_C --> LLM
    PROOF_C -.->|"опционально"| LLM_EXT
    QUEUE --> LLM
    QUEUE --> RAG
    LLM --> DS
    RAG --> API
    J_ORCH --> ORCH
    J_WAIT --> WAIT
    J_DEAD --> ORCH
    J_DEAD --> GEN
    J_IDX --> RAG
    J_TIMER --> ORCH

    classDef ui fill:#E3F2FD,stroke:#1565C0,color:#0D47A1
    classDef core fill:#FFF3E0,stroke:#E65100,color:#BF360C
    classDef integ fill:#F3E5F5,stroke:#6A1B9A,color:#4A148C
    classDef tpl fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20
    classDef proof fill:#FFFDE7,stroke:#F9A825,color:#F57F17
    classDef job fill:#ECEFF1,stroke:#546E7A,color:#263238
    classDef external fill:#FBE9E7,stroke:#BF360C,color:#BF360C
    class UI_DL,UI_ADM,UI_REM ui
    class ORCH,RES,GEN,WAIT,AUD,SESS core
    class QUEUE,LLM,RAG integ
    class TPL_M,TPL_R,TPL_C,TPL_S tpl
    class PROOF_C proof
    class J_ORCH,J_IDX,J_WAIT,J_DEAD,J_TIMER job
    class BASE,API,DS,LLM_EXT,SRC external
```

| Компонент | Ответственность | Статус |
|---|---|---|
| Интерфейс ДЛ | `АИС_РабочееМестоДЛ`, `АИС_ФормаЗадачи`, `АИС_ФормаПроектаДокумента` | Проект |
| Админ-панель | `АИС_АдминПанель`: объекты расширения, сроки, промпты, health, переиндексация | Проект |
| `АИС_ОркестраторЗадач` | Создание задачи, переходы `СостояниеИИ`, версии, блокировки, идемпотентность | Проект |
| `АИС_РазрешительПлейсхолдеров` | Парсер `{{...}}`, прямое поле, запрос в БД, запрос к ДЛ, внешний API, лимиты рекурсии | Проект |
| `АИС_ГенераторДокументов` | Детерминированная подстановка, LLM-улучшение, создание проекта в `ИсходящиеДокументы` | Проект |
| `АИС_РаботаСЛистомОжидания` | `АИС_ЛистОжидания`, базовая задача ДЛ, ответы, сроки ожидания | Проект |
| `АИС_АудитДействийИИ` | Запись промптов, ответов, токенов, стоимости, ошибок и длительности | Проект |
| `АИС_ОчередьЗапросовLLM` | Общий рейт-лимитер: оркестратор > мастер шаблонов > вычитка, единый backoff | Проект |
| `АИС_ИнтеграцияСLLM` | DeepSeek, JSON-режим, retry, валидаторы, выбор модели | Проект |
| `АИС_ИнтеграцияСRAG` | HTTP-клиент RAG-сервиса, service-token, таймауты, retry | Проект |
| `АИС_МастерШаблонов` | Импорт DOCX/текста, извлечение структуры, проверка человеком, публикация | Проект |
| `АИС_ГенераторПравилШаблона` | `ПравилаАвтозаполненияФайлов` и ТЧ `АИС_Плейсхолдеры` | Проект |
| `АИС_ПроверкаШаблона` | Дубли, пропуски, неоднозначности, обязательные поля | Проект |
| `АИС_СравнениеШаблонов` | Text/placeholder/structure/metadata diff, оценка и рекомендация | Проект |
| `АИС_ПроверкаДокумента` | Быстрая проверка без LLM, глубокая LLM-вычитка, квоты | Проект |
| `АИС_ПанельЗамечаний` | Показ замечаний, accept/reject, повторная проверка | Проект |
| `УстановкаПараметровСеанса` | `ТекущееДЛ` через `Пользователи`/`ФизическиеЛица` | Проект |
| Регламентные задания | Оркестрация, индексация RAG, лист ожидания, проверка сроков, генерация триггеров | Проект |
| Отчёты | `АИС_СтатистикаЗадач`, `АИС_ЖурналЗадачи`, `АИС_АнализСрывовСроков` | Проект |
| `АИС_ЗаполнитьДемоДанные` | Демо-ДЛ, должности, шаблоны, обязанности, промпты | Проект Этапа 2 |

## 4. Компоненты RAG-сервиса

Устройство контейнера `RAG API`.

```mermaid
flowchart LR
    subgraph RAG["RAG-сервис (FastAPI)"]
        API["HTTP API<br/>health, search, index"]
        AUTH["Проверка service-token"]
        MODELS["Модели API<br/>Pydantic"]
        CONFIG["Конфигурация<br/>env + parameters.yaml"]
        CHUNK["Чанкинг"]
        GIGA["Клиент GigaChat<br/>OAuth + embeddings"]
        STORE["Хранилище Qdrant"]
    end

    QD[("Qdrant<br/>коллекция ai_scrivener_knowledge_v1")]
    GC["GigaChat API"]

    API --> AUTH
    API --> MODELS
    API --> CONFIG
    API --> CHUNK
    API --> STORE
    API --> GIGA
    STORE -->|"gRPC/HTTP"| QD
    GIGA -->|"HTTPS/OAuth"| GC

    classDef rag fill:#FFF3E0,stroke:#E65100,color:#BF360C
    classDef storage fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20
    classDef external fill:#ECEFF1,stroke:#546E7A,color:#263238
    class API,AUTH,MODELS,CONFIG,CHUNK,GIGA,STORE rag
    class QD storage
    class GC external
```

| Компонент | Файл | Ответственность | Статус |
|---|---|---|---|
| HTTP API | `rag-service/src/rag_service/main.py` | Маршруты `/health`, `/v1/search`, индексация, удаление | Реализован |
| Проверка service-token | `main.py` | `X-Service-Token` для всех методов, кроме `/health` | Реализован |
| Модели API | `models.py` | Схемы запросов и ответов | Реализован |
| Конфигурация | `config.py`, `config/parameters.yaml` | Env, секреты, числовые параметры | Реализован |
| Чанкинг | `chunking.py` | Нормализация, разбиение, overlap | Реализован |
| Клиент GigaChat | `gigachat.py` | OAuth, кэш токена, embeddings, retry | Реализован |
| Хранилище Qdrant | `qdrant_store.py` | Коллекция, payload-индексы, upsert/replace/delete/search | Реализован |

## 5. Границы и допущения

- **Целевая модель.** Диаграммы описывают проект; компоненты расширения на BSL ещё не реализованы. RAG-сервис реализован и проверен на трёх шаблонах.
- **RAG-сервис stateless.** Источник истины — 1С; Qdrant хранит только производный векторный индекс.
- **Qdrant не публикуется наружу.** Доступ к нему есть только у RAG API; RAG API закрыт service-token и TLS/reverse proxy.
- **Секреты.** Ключ DeepSeek и service-token хранятся в безопасном хранилище 1С; GigaChat client_secret — в `.env` RAG-сервиса. В диаграммах секретов нет.
- **Внешние LLM.** DeepSeek используется для генерации и классификации; GigaChat — только для эмбеддингов; локальная LLM — опционально для конфиденциальной вычитки.
- **Граница доверия.** Базовая конфигурация и расширение работают в одном процессе 1С и используют штатную модель прав; RLS расширения опирается на ссылку на базовую задачу.
- **Reverse proxy.** В текущем `deploy/` описан Docker Compose для RAG API и Qdrant; TLS/reverse proxy — проектное требование, отдельный конфиг в репозиторий пока не добавлен.
- **Отчёты и админ-панель.** Показаны как компоненты целевой системы; в MVP они входят в Этап 6.

## Связанные документы

- `plans/implementation_plan.md` §3, §7, §8 — архитектура, RAG-сервис, интеграция с LLM.
- `docs/data-model.md` — объекты расширения и повторно используемые объекты базы.
- `docs/process-diagrams.md` — процессы AS-IS и TO-BE.
- `docs/system-analysis/view-and-scope.md` — границы проекта.
- `docs/system-analysis/stakeholder-map.md` — роли и внешние системы.
