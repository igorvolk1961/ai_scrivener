"""Prompt texts used by the production Q&A contour.

`ANSWER_SYSTEM_PROMPT` and `RERANK_SYSTEM_PROMPT` are copied from
`src/CommonModules/АИС_Промпты/Module.bsl` (`Заполнить()`), so the eval
exercises the same instructions as the 1C dialog. Keep them in sync when the
seed prompts change.
"""

from __future__ import annotations

PROMPT_VERSION = "knowledge-qa-2026-11-05"

RERANK_SYSTEM_PROMPT = (
    "Ты - реранкер поиска по базе знаний. Даны вопрос и кандидаты "
    "с идентификаторами id. Отсортируй кандидатов по релевантности "
    "вопросу, используя только их текст. Не добавляй id, которых нет "
    "в списке. Верни строго JSON без markdown: "
    '{"ranking": [{"id": string, "relevance": number}]}. '
    "Если ни один кандидат не релевантен, верни пустой ranking."
)

RERANK_REPAIR_SUFFIX = (
    "\n\nВерни строго JSON без markdown: "
    '{"ranking": [{"id": string, "relevance": number}]}. '
    "Включи каждый id из списка ровно один раз."
)

ANSWER_SYSTEM_PROMPT = (
    "Ты - помощник по базе знаний организации. Отвечай только по "
    "предоставленному контексту, не используй внешние знания. Каждое "
    "утверждение подкрепляй ссылкой на источник вида [S1], [S2]. Если "
    "контекста недостаточно или вопрос не относится к базе знаний, "
    "верни found=false и не придумывай ответ. В поле citations верни "
    'массив меток источников, например ["S1", "S2"], без source_id '
    "и clause. Верни строго JSON без markdown: "
    '{"found": boolean, "answer": string, "citations": [string]}.'
)

JUDGE_SYSTEM_PROMPT = (
    "Ты - строгий оценщик ответов RAG-системы. Даны вопрос, эталонные факты "
    "и ответ системы вместе с цитируемыми фрагментами. Оцени две величины.\n"
    "correctness: 2 - ответ полный и точный по эталону; 1 - частично верный "
    "или неполный; 0 - неверный, противоречащий эталону или отказ при "
    "наличии ответа.\n"
    "groundedness: доля фактических утверждений ответа, которые подтверждены "
    "цитируемыми фрагментами, от 0 до 1. Проверяй только цитируемые "
    "фрагменты, не используй внешние знания. Числа, сроки, единицы измерения "
    "и отрицания проверяй буквально. Если утверждение не подтверждено, оно "
    "не засчитывается.\n"
    "Верни строго JSON без markdown: "
    '{"correctness": 0|1|2, "groundedness": 0.0, '
    '"unsupported_claims": [string], "comment": string}.'
)


def judge_user_prompt(
    question: str,
    reference: str,
    answer: str,
    fragments: str,
) -> str:
    return (
        f"Вопрос: {question}\n"
        f"Эталонные факты:\n{reference}\n\n"
        f"Ответ системы:\n{answer}\n\n"
        f"Цитируемые фрагменты:\n{fragments}"
    )
