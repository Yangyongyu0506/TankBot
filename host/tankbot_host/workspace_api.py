"""Local editor API. Storage does not execute player files or grant runtime permissions."""
from .workspace import open_store, starter, digest
from .learning import learning_bundle
from .campaign_templates import TEMPLATE_VERSION


class WorkspaceAPI:
    def __init__(self, config, seed=None, directory=None):
        self.config = config
        self.store = open_store(config, seed, directory)
        if config.get("campaign", {}).get("active_level"):
            self.unlock(config)

    def get(self):
        snapshot = self.store.read()
        learning = learning_bundle(self.config)
        learning["upgrade_required"] = bool(self.config.get("campaign", {}).get("active_level")
            and not snapshot["files"].get("campaign_robot.py", "").startswith("# TankBot managed scaffold " + TEMPLATE_VERSION))
        return {"snapshot": snapshot, "limits": self.config["workspace"], "storage": "local-versioned-store",
                "level_id": self.config.get("campaign", {}).get("active_level"), "learning": learning}

    def unlock(self, config):
        """Append newly granted files; explicit migration still handles existing paths."""
        snapshot = self.store.read()
        template_id = "campaign-" + config["campaign"]["active_level"] + "-unlock"
        sources = starter(config)
        missing = {path: source for path, source in sources.items() if path not in snapshot["files"]}
        if template_id not in snapshot["ledger"] or missing:
            plan = self.store.plan(template_id, TEMPLATE_VERSION, sources, snapshot["revision"],
                                   {"level_id": config["campaign"]["active_level"], "required_sdk_profile": "0.1.0"})
            self.store.apply(plan["plan_id"], snapshot["revision"], {})
        self.config = config
        return self.get()

    def post(self, operation, value):
        if operation == "save":
            return self.store.edit(value["revision"], value["changes"])
        if operation == "template":
            template_id = "campaign-starter" if self.config.get("campaign", {}).get("active_level") else "odometry-starter"
            return self.store.plan(template_id, TEMPLATE_VERSION, starter(self.config), value["revision"],
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
