"""Local editor API. Storage does not execute player files or grant runtime permissions."""
from .workspace import open_store, starter, digest


class WorkspaceAPI:
    def __init__(self, config, seed=None, directory=None):
        self.config = config
        self.store = open_store(config, seed, directory)

    def get(self):
        return {"snapshot": self.store.read(), "limits": self.config["workspace"], "storage": "local-versioned-store"}

    def post(self, operation, value):
        if operation == "save":
            return self.store.edit(value["revision"], value["changes"])
        if operation == "template":
            return self.store.plan("odometry-starter", "1.0.0", starter(self.config), value["revision"],
                                   {"required_sdk_profile": "0.1.0", "module_contract": f"contracts/{self.config['module']['module_id']}.json",
                                    "purpose": "single-module odometry project and tests"})
        if operation == "import":
            files = value["files"]
            return self.store.plan("import", digest(files), files, value["revision"])
        if operation == "apply":
            return self.store.apply(value["plan_id"], value["revision"], value["resolutions"])
        if operation == "revision":
            return self.store.read(value["revision"])
        if operation == "archive":
            return self.store.archive(value["revision"], value["record"])
        if operation == "archives":
            return self.store.archives()
        raise ValueError("UNKNOWN_WORKSPACE_OPERATION")
