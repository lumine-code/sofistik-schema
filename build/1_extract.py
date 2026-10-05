"""Extract ordered command schemas from installed SOFiSTiK ``.err`` files.

The extractor writes ``sofistik.<release>.<language>.schema.json`` for every
release and language. Each file preserves every alternative command form and
every positional slot within it, including repeated names and placeholders.
Compact keyword indexes are generated from these canonical schemas by
``scripts/generate-data.js``.

The ``.err`` files are proprietary installation data. ``0_copyerr.py`` copies
them into ignored build directories; only the derived JSON is checked in.
"""

from __future__ import annotations

import copy
import json
import re
from collections import defaultdict, deque
from pathlib import Path


LANGUAGES = ("de", "en")
UNIVERSAL_COMMANDS = {"de": "SEIT", "en": "PAGE"}
METADATA_PATH = Path(__file__).resolve().parent.parent / "schema" / "meta.json"
METADATA = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
VERSIONS = METADATA["versions"]
SOURCE_MODULE_ALIASES = METADATA["sourceModuleAliases"]

COMMAND_RE = re.compile(
    r"^-(10|20|\*0)(=|\s)([A-Z][A-Z0-9]{0,3})(?=[\s\'\"!`=]|$)(.*)$",
    re.IGNORECASE,
)
CONTINUATION_RE = re.compile(r"^-(10|20|\*0)\s{2,}(.+)$", re.IGNORECASE)
DATA_TYPE_RE = re.compile(r"^-(1|2|\*)0?2(?:\s|$)", re.IGNORECASE)
ENUM_RE = re.compile(
    r"^-(1|2|\*)(1)([0-9A-Z])\s*(.*)$", re.IGNORECASE
)
DOC_RE = re.compile(r"^-(\*7|17|27)\s+([A-Z]{1,4})\s+(.*)$", re.IGNORECASE)
REDIRECT_RE = re.compile(
    r"^->\s*([A-Z][A-Z0-9_]{0,3})(?:\s*@\s*([A-Z][A-Z0-9]{0,3}))?\s*$",
    re.IGNORECASE,
)
PARAM_RE = re.compile(
    r"(?:(?P<prefix>[\"'`=!])"
    r"(?:(?P<prefixed_placeholder>XXXX|NONE|\.{4})|"
    r"(?P<prefixed_name>[A-Z][A-Z0-9_+/\-]{0,3})(?![A-Z0-9_+/\-])))|"
    r"(?<![A-Z0-9_+/\-])(?:(?P<placeholder>XXXX|NONE|\.{4})|"
    r"(?P<name>[A-Z][A-Z0-9_+/\-]{0,3})(?![A-Z0-9_+/\-]))",
    re.IGNORECASE,
)
ENUM_VALUE_RE = re.compile(r"^[A-Z0-9_().=*+/\->]+$", re.IGNORECASE)


def read_err_lines(filepath: Path) -> list[str]:
    """Read an error catalogue using the first encoding that decodes it."""

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return filepath.read_text(encoding=encoding).splitlines()
        except UnicodeDecodeError:
            continue
    print(f"    Warning: could not decode {filepath}")
    return []


def mask_documentation(text: str) -> str:
    """Blank prose constructs without changing source columns."""

    for pattern in (r"\([^)]*\)", r"\[[^\]]*\]"):
        text = re.sub(pattern, lambda match: " " * len(match.group(0)), text)
    return text


def extract_param_slots(
    text: str, start_column: int = 0, start_position: int = 1
) -> list[dict]:
    """Return positional slots from one definition line.

    Slot names are deliberately not deduplicated. The private ``_column``
    value retains fixed-column alignment for the following ``-*2`` row and is
    removed before serialization.
    """

    slots = []
    masked = mask_documentation(text)
    for match in PARAM_RE.finditer(masked):
        placeholder = match.group("prefixed_placeholder") or match.group("placeholder")
        prefix = match.group("prefix") or ""
        matched_name = match.group("prefixed_name") or match.group("name")
        name = None if placeholder else matched_name.upper()

        if placeholder:
            kind = "placeholder"
        elif prefix == '"':
            kind = "enum"
        elif prefix == "'":
            kind = "literal"
        elif prefix == "`":
            kind = "comment"
        else:
            kind = "keyword"

        slots.append(
            {
                "position": start_position + len(slots),
                "name": name,
                "kind": kind,
                "nativePrefix": prefix,
                "dataTypeCode": None,
                "enumValues": set(),
                "enumRedirect": None,
                "_column": start_column + match.start(),
            }
        )
    return slots


def extract_enum_values(text: str) -> list[str]:
    """Extract enum tokens while preserving first-occurrence order.

    Enum rows use whitespace-separated tokens rather than identifier syntax.
    Values may therefore begin with a number or contain punctuation, including
    ``2D``, ``SIG+``, ``PT/P``, ``A6.1`` and ``(D)``. Apostrophes delimit
    adjacent fixed-width cells in a few legacy catalogues. The exact ``obs.``
    marker is a catalogue annotation rather than a public enum value.
    """

    values = []
    seen = set()
    for token in re.split(r"[\s']+", text.strip()):
        value = token.upper()
        if (
            not value
            or value == "XXXX"
            or value == "OBS."
            or re.fullmatch(r"\.{2,}\d*", value)
            or not ENUM_VALUE_RE.fullmatch(value)
        ):
            continue
        if value not in seen:
            values.append(value)
            seen.add(value)
    return values


def extract_bracket_enums(text: str) -> list[str]:
    """Extract the compact ``[A|B|C]`` enum form from help rows."""

    match = re.search(r"\[([^\]]+)\]", text)
    if not match:
        return []

    values = []
    seen = set()
    for item in match.group(1).split("|"):
        value = item.strip().upper()
        if not ENUM_VALUE_RE.fullmatch(value):
            continue
        if (
            value == "XXXX"
            or value == "OBS."
            or re.fullmatch(r"\.{2,}\d*", value)
            or value in seen
        ):
            continue
        values.append(value)
        seen.add(value)
    return values


def command_template(name: str) -> dict:
    return {"de": name, "en": name, "forms_de": [], "forms_en": []}


def append_form(command: dict, language: str, text: str, start_column: int) -> tuple[dict, list[dict]]:
    """Append one source definition as a distinct command form."""

    slots = extract_param_slots(text, start_column)
    form = {"slots": slots}
    command[f"forms_{language}"].append(form)
    return form, slots


def append_segment(form: dict, text: str, start_column: int) -> list[dict]:
    """Append a continuation segment to one active command form."""

    slots = form["slots"]
    segment = extract_param_slots(text, start_column, len(slots) + 1)
    slots.extend(segment)
    return segment


def target_slot(slots: list[dict], code: str) -> dict | None:
    """Resolve a base-36 position selector to one slot."""

    try:
        position = int(code, 36)
    except ValueError:
        return None
    return next((slot for slot in slots if slot["position"] == position), None)


def assign_data_types(segment: list[dict], line: str) -> None:
    """Attach fixed-column ``-*2`` codes to the latest definition segment."""

    if not segment:
        return
    for match in re.finditer(r"(?<!\d)\d{4}(?!\d)", line[3:]):
        column = match.start() + 3
        candidates = [slot for slot in segment if slot["_column"] <= column]
        if candidates:
            max(candidates, key=lambda slot: slot["_column"])["dataTypeCode"] = match.group(0)


def language_targets(prefix: str) -> tuple[str, ...]:
    if prefix == "1":
        return ("de",)
    if prefix == "2":
        return ("en",)
    return LANGUAGES


def parse_err_file(filepath: Path | str) -> dict:
    """Parse one ``.err`` catalogue into paired German and English schemas."""

    filepath = Path(filepath)
    lines = read_err_lines(filepath)
    result = {"module": "", "version": "", "commands": {}}
    if not lines:
        return result

    header_match = re.match(r"^0000([A-Z0-9_]+?)\s*SOFiSTiK", lines[0], re.IGNORECASE)
    if header_match:
        result["module"] = header_match.group(1).upper()
    if len(lines) > 1:
        version_match = re.match(r"^0000VERSION\s+(\d+)", lines[1], re.IGNORECASE)
        if version_match:
            result["version"] = version_match.group(1)

    current_key = None
    pending_german_forms = deque()
    active_german_occurrence = None
    active_forms = {"de": None, "en": None}
    last_segments = {"de": [], "en": []}

    for line in lines:
        command_match = COMMAND_RE.match(line)
        if command_match:
            language_code = command_match.group(1)
            separator = command_match.group(2)
            command_name = command_match.group(3).upper()
            rest = command_match.group(4)
            is_reference = (separator == "=" and not rest.strip()) or rest.strip() == "="

            if language_code == "10":
                current_key = command_name
                command = result["commands"].setdefault(current_key, command_template(command_name))
                command["de"] = command_name
                if is_reference:
                    active_forms["de"] = None
                    last_segments["de"] = []
                else:
                    active_forms["de"], last_segments["de"] = append_form(
                        command, "de", rest, command_match.start(4)
                    )
                active_german_occurrence = {
                    "key": current_key,
                    "form": active_forms["de"],
                    "segment": last_segments["de"],
                }
                pending_german_forms.append(active_german_occurrence)
                active_forms["en"] = None
                last_segments["en"] = []
            elif language_code == "20":
                paired_german = (
                    pending_german_forms.popleft() if pending_german_forms else None
                )
                current_key = paired_german["key"] if paired_german else command_name
                active_forms["de"] = (
                    paired_german["form"] if paired_german else None
                )
                last_segments["de"] = (
                    paired_german["segment"] if paired_german else []
                )
                active_german_occurrence = paired_german
                command = result["commands"].setdefault(current_key, command_template(command_name))
                command["en"] = command_name
                if is_reference:
                    active_forms["en"] = None
                    last_segments["en"] = []
                else:
                    active_forms["en"], last_segments["en"] = append_form(
                        command, "en", rest, command_match.start(4)
                    )
            else:
                current_key = command_name
                active_german_occurrence = None
                command = result["commands"].setdefault(current_key, command_template(command_name))
                command["de"] = command_name
                command["en"] = command_name
                if is_reference:
                    for language in LANGUAGES:
                        active_forms[language] = None
                        last_segments[language] = []
                else:
                    for language in LANGUAGES:
                        active_forms[language], last_segments[language] = append_form(
                            command, language, rest, command_match.start(4)
                        )
            continue

        data_type_match = DATA_TYPE_RE.match(line)
        if data_type_match:
            for language in language_targets(data_type_match.group(1)):
                assign_data_types(last_segments[language], line)
            continue

        enum_match = ENUM_RE.match(line)
        if enum_match and current_key in result["commands"]:
            prefix = enum_match.group(1)
            selector = enum_match.group(3)
            body = enum_match.group(4).strip()
            redirect_match = REDIRECT_RE.match(body)
            enum_values = [] if redirect_match else extract_enum_values(body)
            command = result["commands"][current_key]

            for language in language_targets(prefix):
                form = active_forms[language]
                if form is None:
                    continue
                slot = target_slot(form["slots"], selector)
                if slot is None:
                    continue
                if redirect_match:
                    item_name = redirect_match.group(1).upper()
                    redirect_command = redirect_match.group(2)
                    slot["enumRedirect"] = {
                        "command": (
                            redirect_command.upper() if redirect_command else command[language]
                        ),
                        "item": item_name,
                    }
                else:
                    slot["enumValues"].update(enum_values)
            continue

        doc_match = DOC_RE.match(line)
        if doc_match and current_key in result["commands"]:
            language_code, body = doc_match.group(1), doc_match.group(3)
            values = extract_bracket_enums(body)
            prefix = "*" if language_code == "*7" else language_code[0]
            command = result["commands"][current_key]
            for language in language_targets(prefix):
                form = active_forms[language]
                if form is None:
                    continue
                for slot in form["slots"]:
                    if slot["name"] == "OPT":
                        slot["enumValues"].update(values)
            continue

        continuation_match = CONTINUATION_RE.match(line)
        if continuation_match and current_key in result["commands"]:
            language_code = continuation_match.group(1)
            body = continuation_match.group(2)
            if language_code == "10":
                if active_forms["de"] is not None:
                    last_segments["de"] = append_segment(
                        active_forms["de"], body, continuation_match.start(2)
                    )
                    if active_german_occurrence is not None:
                        active_german_occurrence["segment"] = last_segments["de"]
            elif language_code == "20":
                if active_forms["en"] is not None:
                    last_segments["en"] = append_segment(
                        active_forms["en"], body, continuation_match.start(2)
                    )
            else:
                for language in LANGUAGES:
                    if active_forms[language] is not None:
                        last_segments[language] = append_segment(
                            active_forms[language], body, continuation_match.start(2)
                        )
                if active_german_occurrence is not None:
                    active_german_occurrence["segment"] = last_segments["de"]

    return result


def parse_all_err_files(errs_dir: Path | str) -> dict:
    """Parse every catalogue in a release directory."""

    commands = {}
    for err_file in sorted(Path(errs_dir).glob("*.err")):
        print(f"  Parsing {err_file.name}...")
        data = parse_err_file(err_file)
        module_name = data["module"] or err_file.stem.upper()
        module_name = SOURCE_MODULE_ALIASES.get(module_name, module_name)
        if data["commands"]:
            commands[module_name] = data["commands"]
    return commands


def serialize_slot(slot: dict) -> dict:
    return {
        "position": slot["position"],
        "name": slot["name"],
        "kind": slot["kind"],
        "nativePrefix": slot.get("nativePrefix"),
        "dataTypeCode": slot["dataTypeCode"],
        "enumValues": sorted(slot["enumValues"]),
        "enumRedirect": copy.deepcopy(slot["enumRedirect"]),
    }


def serialize_form(form: dict) -> dict:
    return {"slots": [serialize_slot(slot) for slot in form["slots"]]}


def deduplicate_forms(forms: list[dict]) -> list[dict]:
    """Remove semantically identical forms while preserving source order."""

    result = []
    seen = set()
    for form in forms:
        fingerprint = json.dumps(form, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(form)
    return result


def deduplicate_schema_forms(schema: dict) -> None:
    for commands in schema.values():
        for command in commands.values():
            command["forms"] = deduplicate_forms(command["forms"])


def command_slots(command: dict):
    for form in command["forms"]:
        yield from form["slots"]


def build_language_schema(all_commands: dict, language: str) -> tuple[dict, set[str]]:
    """Build one localized schema and distribute SOFISTIK references."""

    modules = {}
    for module_name, commands in all_commands.items():
        modules[module_name] = {}
        for command in commands.values():
            localized_name = command[language]
            localized = modules[module_name].setdefault(localized_name, {"forms": []})
            localized["forms"].extend(
                serialize_form(form) for form in command[f"forms_{language}"]
            )

    deduplicate_schema_forms(modules)

    sofistik = modules.get("SOFISTIK", {})
    universal_command = UNIVERSAL_COMMANDS[language]
    universal_forms = [
        copy.deepcopy(form)
        for module_name, commands in modules.items()
        if module_name != "SOFISTIK"
        for form in commands.get(universal_command, {}).get("forms", [])
        if form["slots"]
    ]
    if universal_forms:
        universal_schema = sofistik.setdefault(universal_command, {"forms": []})
        universal_schema["forms"].extend(universal_forms)
        universal_schema["forms"] = deduplicate_forms(universal_schema["forms"])

    filled = defaultdict(set)
    for module_name, commands in modules.items():
        if module_name == "SOFISTIK":
            continue
        for command_name, schema in list(commands.items()):
            shared_schema = sofistik.get(command_name)
            shared_has_slots = shared_schema and any(
                form["slots"] for form in shared_schema["forms"]
            )
            is_reference = not schema["forms"] or (
                shared_has_slots and all(not form["slots"] for form in schema["forms"])
            )
            if (
                is_reference
                and shared_schema
                and shared_schema["forms"]
            ):
                commands[command_name] = copy.deepcopy(shared_schema)
                filled[command_name].add(module_name)

    for command_name in filled:
        if command_name not in {universal_command, "END", "ENDE"}:
            sofistik.pop(command_name, None)

    if "SOFISTIK" in modules:
        modules["BASIC"] = modules.pop("SOFISTIK")
    modules.setdefault("TEMPLATE", {})

    echo_schema = {
        "forms": [
            {
                "slots": [
                    {
                        "position": 1,
                        "name": "OPT",
                        "kind": "keyword",
                        "nativePrefix": None,
                        "dataTypeCode": None,
                        "enumValues": [],
                        "enumRedirect": None,
                    },
                    {
                        "position": 2,
                        "name": "VAL",
                        "kind": "keyword",
                        "nativePrefix": None,
                        "dataTypeCode": None,
                        "enumValues": [],
                        "enumRedirect": None,
                    },
                ]
            }
        ]
    }
    for commands in modules.values():
        commands.setdefault("ECHO", copy.deepcopy(echo_schema))

    return modules, set(filled)


def find_redirect_values(schema: dict, module_name: str, redirect: dict) -> set[str] | None:
    """Find a redirect target in its module, then in BASIC."""

    command_name = redirect["command"]
    item_name = redirect["item"]
    command = schema.get(module_name, {}).get(command_name)
    if command is None:
        command = schema.get("BASIC", {}).get(command_name)
    if command is None:
        return None

    target_slots = [slot for slot in command_slots(command) if slot["name"] == item_name]
    if not target_slots:
        return None
    return {value for slot in target_slots for value in slot["enumValues"]}


def resolve_enum_redirects(schema: dict) -> tuple[int, int]:
    """Resolve redirect chains while retaining their provenance."""

    redirect_slots = [
        (module_name, slot)
        for module_name, commands in schema.items()
        for command in commands.values()
        for slot in command_slots(command)
        if slot["enumRedirect"] is not None
    ]

    for _ in range(len(redirect_slots) + 1):
        changed = False
        for module_name, slot in redirect_slots:
            values = find_redirect_values(schema, module_name, slot["enumRedirect"])
            if not values:
                continue
            merged = sorted(set(slot["enumValues"]) | values)
            if merged != slot["enumValues"]:
                slot["enumValues"] = merged
                changed = True
        if not changed:
            break

    deduplicate_schema_forms(schema)
    final_redirect_slots = [
        slot
        for commands in schema.values()
        for command in commands.values()
        for slot in command_slots(command)
        if slot["enumRedirect"] is not None
    ]
    unresolved = sum(not slot["enumValues"] for slot in final_redirect_slots)
    return len(final_redirect_slots), unresolved


def write_json(filepath: Path, data: object) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def process_version(version: str, build_dir: Path, output_dir: Path) -> dict:
    """Extract both localized views for one installed release."""

    errs_dir = build_dir / version
    if not errs_dir.is_dir():
        raise FileNotFoundError(f"Missing source catalogue directory for {version}: {errs_dir}")

    print(f"\nProcessing version {version}...")
    all_commands = parse_all_err_files(errs_dir)
    if not all_commands:
        raise RuntimeError(f"No commands found for {version} in {errs_dir}")

    stats = {
        "modules": len(all_commands),
        "commands": sum(len(commands) for commands in all_commands.values()),
        "languages": {},
    }
    for language in LANGUAGES:
        schema, filled_commands = build_language_schema(all_commands, language)
        redirect_count, unresolved_count = resolve_enum_redirects(schema)
        write_json(output_dir / f"sofistik.{version}.{language}.schema.json", schema)

        form_count = sum(
            len(command["forms"])
            for module in schema.values()
            for command in module.values()
        )
        slot_count = sum(
            len(form["slots"])
            for module in schema.values()
            for command in module.values()
            for form in command["forms"]
        )
        stats["languages"][language] = {
            "forms": form_count,
            "slots": slot_count,
            "redirects": redirect_count,
            "unresolvedRedirects": unresolved_count,
            "filledCommands": len(filled_commands),
        }
        print(
            f"  {language.upper()}: {form_count} forms, {slot_count} slots, "
            f"{redirect_count} redirects "
            f"({unresolved_count} unresolved), {len(filled_commands)} references filled"
        )

    return stats


def clear_extracted_schemas(output_dir: Path) -> None:
    """Remove only intermediate schema files produced by an earlier run."""

    if not output_dir.is_dir():
        return
    for schema_file in output_dir.glob("sofistik.*.schema.json"):
        if schema_file.is_file():
            schema_file.unlink()


def main() -> dict:
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "extracted"

    print("SOFiSTiK Command and Schema Extractor")
    print("=" * 50)
    clear_extracted_schemas(output_dir)

    results = {}
    try:
        for version in VERSIONS:
            results[version] = process_version(version, script_dir, output_dir)
    except BaseException:
        clear_extracted_schemas(output_dir)
        raise

    print("\n" + "=" * 50)
    print("Summary:")
    for version, result in results.items():
        language_summary = ", ".join(
            f"{language.upper()} {stats['forms']} forms/{stats['slots']} slots/"
            f"{stats['unresolvedRedirects']} unresolved"
            for language, stats in result["languages"].items()
        )
        print(
            f"  {version}: {result['modules']} modules, {result['commands']} commands; "
            f"{language_summary}"
        )
    print("\nDone!")
    return results


if __name__ == "__main__":
    main()
