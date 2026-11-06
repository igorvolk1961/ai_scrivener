from __future__ import annotations

import re
import sys
from pathlib import Path

FORMS: dict[str, tuple[str, ...]] = {
    "DataProcessors/АИС_ВопросПоБазеЗнаний/Forms/Форма/Ext/Form.xml": (
        "Диалоги",
        "Настройки",
        "Ответ",
        "Вопрос",
        "ФрагментТекст",
        "ТаблицаЦитатПредставление",
    ),
}


def main() -> int:
    root = Path(sys.argv[1])
    for relative, fields in FORMS.items():
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for name in fields:
            pattern = re.compile(
                rf'(<InputField name="{re.escape(name)}".*?</InputField>)',
                re.DOTALL,
            )
            text, count = pattern.subn(_enable_wrap, text, count=1)
            if count != 1:
                raise SystemExit(f"field not found: {relative}: {name}")
        text = _enable_table_scroll(text)
        path.write_text(text, encoding="utf-8")
    return 0


def _enable_table_scroll(text: str) -> str:
    pattern = re.compile(
        r'(<Table name="ТаблицаЦитат".*?</Table>)',
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        block = match.group(1)
        block = block.replace(
            "<VerticalScrollBar>DontUse</VerticalScrollBar>",
            "<VerticalScrollBar>AutoUse</VerticalScrollBar>",
            1,
        )
        return block

    text, count = pattern.subn(replace, text, count=1)
    if count != 1:
        raise SystemExit("citation table not found")
    return text


def _enable_wrap(match: re.Match[str]) -> str:
    block = match.group(1)
    if "<Wrap>false</Wrap>" in block:
        return block.replace("<Wrap>false</Wrap>", "<Wrap>true</Wrap>", 1)
    if "<Wrap>true</Wrap>" in block:
        return block
    raise SystemExit("Wrap property not found in field")


if __name__ == "__main__":
    raise SystemExit(main())
