from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION_MDO = REPO_ROOT / "src" / "Configuration" / "Configuration.mdo"
PROJECT_PMF = REPO_ROOT / "DT-INF" / "PROJECT.PMF"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_text(root: ET.Element, name: str) -> str | None:
    for child in root:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return None


def _read_pmf() -> dict[str, str]:
    if not PROJECT_PMF.is_file():
        raise ValueError(f"missing {PROJECT_PMF}")
    result: dict[str, str] = {}
    for line in PROJECT_PMF.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def main() -> int:
    errors: list[str] = []

    if not CONFIGURATION_MDO.is_file():
        errors.append(f"missing {CONFIGURATION_MDO}")
    else:
        try:
            root = ET.parse(CONFIGURATION_MDO).getroot()
        except ET.ParseError as error:
            errors.append(f"cannot parse {CONFIGURATION_MDO}: {error}")
        else:
            if _local_name(root.tag) != "Configuration":
                errors.append(f"unexpected root element in {CONFIGURATION_MDO}: {root.tag}")
            name = _find_text(root, "name")
            prefix = _find_text(root, "namePrefix")
            compatibility = _find_text(root, "configurationExtensionCompatibilityMode")
            if not name:
                errors.append("Configuration.mdo has no <name>")
            if not prefix:
                errors.append("Configuration.mdo has no <namePrefix>")
            if not compatibility:
                errors.append("Configuration.mdo has no <configurationExtensionCompatibilityMode>")

    try:
        pmf = _read_pmf()
    except ValueError as error:
        errors.append(str(error))
    else:
        base_project = pmf.get("Base-Project", "")
        runtime_version = pmf.get("Runtime-Version", "")
        if not base_project:
            errors.append("PROJECT.PMF has no Base-Project")
        if not runtime_version:
            errors.append("PROJECT.PMF has no Runtime-Version")
        if CONFIGURATION_MDO.is_file():
            try:
                root = ET.parse(CONFIGURATION_MDO).getroot()
            except ET.ParseError:
                pass
            else:
                compatibility = _find_text(root, "configurationExtensionCompatibilityMode")
                if compatibility and runtime_version and compatibility != runtime_version:
                    errors.append(
                        "compatibility mismatch: "
                        f"Configuration.mdo={compatibility}, PROJECT.PMF={runtime_version}"
                    )

    if errors:
        for message in errors:
            print(f"extension manifest: {message}", file=sys.stderr)
        return 1

    print("extension manifest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
