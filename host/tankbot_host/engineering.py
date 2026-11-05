"""Shared, validated quotas for local engineering tools; never a gameplay parameter source."""
from functools import lru_cache
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def settings():
    prepared=ROOT/'config/engineering.json'
    if prepared.exists():value=json.loads(prepared.read_text())
    else:
        from .configuration import load_yaml
        value=load_yaml(ROOT/'config/engineering.yaml')
    from jsonschema import Draft202012Validator
    schema=json.loads((ROOT/'docs/schemas/engineering.schema.json').read_text())
    Draft202012Validator(schema).validate(value)
    return value
