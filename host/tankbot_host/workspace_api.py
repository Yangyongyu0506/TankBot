"""Local editor API. Storage does not execute player files or grant runtime permissions."""
from .workspace import open_store, starter, digest, workspace_scope
from .learning import learning_bundle
from .campaign_templates import template_version, framework_upgrade
from pathlib import Path


def select_workspace(config, scopes, directory=None):
    """Select a course project without merging code across declared scopes."""
    scope=workspace_scope(config)
    if scope in scopes:
        api=scopes[scope]
        api.unlock(config)
        return api
    target=None
    if directory is not None:
        target=Path(directory) if None in scopes and scope=="campaign" else Path(directory)/"scopes"/scope
    api=WorkspaceAPI(config,directory=target)
    scopes[scope]=api
    return api


class WorkspaceAPI:
    def __init__(self, config, seed=None, directory=None):
        self.config = config
        self.store = open_store(config, seed, directory)
        if config.get("campaign", {}).get("active_level"):
            self.unlock(config)

    def get(self):
        snapshot = self.store.read()
        learning = learning_bundle(self.config)
        learning["upgrade"] = framework_upgrade(self.config, snapshot["files"], snapshot["ledger"])
        learning["upgrade_required"] = learning["upgrade"]["required"]
        return {"snapshot": snapshot, "limits": self.config["workspace"], "storage": "local-versioned-store",
                "level_id": self.config.get("campaign", {}).get("active_level"), "learning": learning}

    def unlock(self, config):
        """Append newly granted files; explicit migration still handles existing paths."""
        if workspace_scope(config) != workspace_scope(self.config):
            raise ValueError("WORKSPACE_SCOPE_MISMATCH: 请打开本课程的独立工作区；未合并或修改已有代码。")
        snapshot = self.store.read()
        template_id = "campaign-" + config["campaign"]["active_level"] + "-unlock"
        sources = starter(config)
        missing = {path: source for path, source in sources.items() if path not in snapshot["files"]}
        if template_id not in snapshot["ledger"] or missing:
            plan = self.store.plan(template_id, template_version(config), sources, snapshot["revision"],
                                   {"level_id": config["campaign"]["active_level"], "required_sdk_profile": "0.1.0"})
            self.store.apply(plan["plan_id"], snapshot["revision"], {})
        self.config = config
        return self.get()

    def post(self, operation, value):
        if operation == "save":
            return self.store.edit(value["revision"], value["changes"])
        if operation == "upgrade":
            if not self.config.get("campaign", {}).get("active_level"):
                raise ValueError("NO_TEACHING_UPGRADE")
            snapshot = self.store.read()
            sources = starter(self.config)
            upgrade = framework_upgrade(self.config,snapshot["files"],snapshot["ledger"])
            managed = upgrade["managed_files"]
            untouched = upgrade.get("generated_algorithm_files", [])
            # Authored algorithms never enter the plan. A ledger-identical generated
            # stub may be offered, but only changed through the explicit preview/apply.
            sources = {path: source for path, source in sources.items()
                       if path in managed or path in untouched or path not in snapshot["files"]}
            plan = self.store.plan("campaign-starter", template_version(self.config), sources, value["revision"],
                                   {"purpose": "teaching-framework-upgrade", "preserve_existing_algorithms": True,
                                    "untouched_generated_algorithms": untouched})
            plan["purpose"] = "teaching-framework-upgrade"
            plan["message"] = upgrade["message"]
            plan["generated_algorithm_files"] = untouched
            return plan
        if operation == "template":
            template_id = "campaign-starter" if self.config.get("campaign", {}).get("active_level") else "odometry-starter"
            return self.store.plan(template_id, template_version(self.config), starter(self.config), value["revision"],
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
