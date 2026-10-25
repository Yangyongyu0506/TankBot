"""Read trusted YAML configuration, rejecting ambiguous keys and non-JSON values."""
import json
from pathlib import Path


def load_yaml(path, *, content=None):
    import yaml
    class Loader(yaml.SafeLoader):
        pass
    def mapping(loader, node):
        result = {}
        for key, value in node.value:
            key = loader.construct_object(key, deep=True)
            if not isinstance(key, str) or key in result:
                raise ValueError("Configuration YAML contains duplicate/non-string keys")
            result[key] = loader.construct_object(value, deep=True)
        return result
    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        data = yaml.load(Path(path).read_text(encoding="utf-8") if content is None else content, Loader=Loader)
        # Disallow cyclic aliases, non-finite numbers, dates and Python-specific values.
        return json.loads(json.dumps(data, allow_nan=False))
    except (yaml.YAMLError, RecursionError, TypeError) as error:
        raise ValueError("Invalid configuration YAML: " + str(path)) from error
