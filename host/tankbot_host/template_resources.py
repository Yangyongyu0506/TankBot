"""Read-only, repository-owned Python scaffold resources; YAML selects registered components."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]


def load_template_resource(name):
    if not isinstance(name,str) or not re.fullmatch(r'[a-z_]+/[a-z_]+\.py',name):
        raise ValueError('INVALID_TEMPLATE_RESOURCE')
    return (ROOT/'templates'/name).read_text(encoding='utf-8')
