"""Preserve historical gameplay fixtures while allowing the approved editor UI wording."""
import json
from pathlib import Path

CHANGES = json.loads((Path(__file__).parent / 'fixtures/external-editor-text-changes.json').read_text())
PREVIOUS = {item['after']: item['before'] for item in CHANGES}
assert len(PREVIOUS) == len({(item['after'], item['before']) for item in CHANGES})


def legacy_editor_instructions(value):
    if isinstance(value, dict):
        return {key: legacy_editor_instructions(item) for key, item in value.items()}
    if isinstance(value, list):
        return [legacy_editor_instructions(item) for item in value]
    return PREVIOUS.get(value, value) if isinstance(value, str) else value
