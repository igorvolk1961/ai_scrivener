"""Patch the exported folder form.

EDT silently drops table-level properties (header, scroll bars, stretch)
from this hand-written form, and it does not expose form-command buttons in
the auto command bar. Apply both after the regular EDT export.
"""
from __future__ import annotations

import sys
from pathlib import Path

HEADER = """\t\t\t<Representation>List</Representation>
\t\t\t<ChangeRowSet>false</ChangeRowSet>
\t\t\t<ChangeRowOrder>false</ChangeRowOrder>
\t\t\t<AutoMaxWidth>false</AutoMaxWidth>
\t\t\t<AutoMaxHeight>false</AutoMaxHeight>
\t\t\t<AutoMaxRowsCount>false</AutoMaxRowsCount>
\t\t\t<SelectionMode>SingleRow</SelectionMode>
\t\t\t<Header>true</Header>
\t\t\t<HeaderHeight>1</HeaderHeight>
\t\t\t<FooterHeight>1</FooterHeight>
\t\t\t<HorizontalScrollBar>AutoUse</HorizontalScrollBar>
\t\t\t<VerticalScrollBar>AutoUse</VerticalScrollBar>
\t\t\t<HorizontalLines>true</HorizontalLines>
\t\t\t<VerticalLines>true</VerticalLines>
\t\t\t<SearchOnInput>Use</SearchOnInput>
\t\t\t<InitialListView>Beginning</InitialListView>
\t\t\t<HorizontalStretch>true</HorizontalStretch>
\t\t\t<VerticalStretch>true</VerticalStretch>
\t\t\t<FileDragMode>AsFile</FileDragMode>
"""

SORT_BUTTONS = [
    ("СортДокумент", "Документ"),
    ("СортДата", "Дата"),
    ("СортНазначение", "Назначение"),
    ("СортТип", "Тип"),
    ("СортПапки", "Папки"),
]


def sort_buttons() -> str:
    result = []
    for index, (name, title) in enumerate(SORT_BUTTONS, start=50):
        result.append(
            f"""\t\t\t<Button name="{name}" id="{index}">
\t\t\t\t<Type>CommandBarButton</Type>
\t\t\t\t<CommandName>Form.Command.{name}</CommandName>
\t\t\t\t<Title>
\t\t\t\t\t<v8:item>
\t\t\t\t\t\t<v8:lang>ru</v8:lang>
\t\t\t\t\t\t<v8:content>{title}</v8:content>
\t\t\t\t\t</v8:item>
\t\t\t\t</Title>
\t\t\t</Button>
"""
        )
    return "".join(result)


def patch_table(text: str) -> str:
    marker = '<Table name="ТаблицаДокументов" id="8">'
    start = text.find(marker)
    if start < 0:
        return text
    data_path = text.find("<DataPath>", start)
    if data_path < 0:
        return text
    opening_end = start + len(marker)
    text = text[:opening_end] + "\n" + HEADER + "\t\t\t" + text[data_path:]
    start = text.find(marker)
    end = text.find("</Table>", start)
    if start < 0 or end < 0:
        return text
    table = text[start:end]
    # Column titles must be visible in the header.
    table = table.replace("<TitleLocation>None</TitleLocation>", "<TitleLocation>Top</TitleLocation>")
    return text[:start] + table + text[end:]


def patch_auto_command_bar(text: str) -> str:
    marker = '<AutoCommandBar name="ФормаКоманднаяПанель" id="-1"/>'
    if marker not in text:
        return text
    block = (
        '<AutoCommandBar name="ФормаКоманднаяПанель" id="-1">\n'
        "\t\t<ChildItems>\n"
        + sort_buttons()
        + "\t\t</ChildItems>\n"
        "\t</AutoCommandBar>"
    )
    return text.replace(marker, block, 1)


def patch(path: Path) -> bool:
    text = path.read_text()
    text = patch_table(text)
    text = patch_auto_command_bar(text)
    path.write_text(text)
    return True


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_folder_form.py <export-dir>")
    form = Path(sys.argv[1]) / (
        "DataProcessors/АИС_ПапкиДокументов/Forms/Форма/Ext/Form.xml"
    )
    if not patch(form):
        raise SystemExit(f"folder form not found or not patched: {form}")
    print(f"Patched folder form: {form}")


if __name__ == "__main__":
    main()
