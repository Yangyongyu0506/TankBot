"""Weapons chapter scaffolds: numerical algorithms stay in player-owned files."""
from .template_resources import load_template_resource

AUTO_AIM: str = load_template_resource("weapons/legacy_auto_aim.py")

POSE_TRACKER: str = load_template_resource("weapons/pose_tracker.py")

ARMOR_AIM: str = load_template_resource("weapons/armor_aim.py")

MODULES: str = load_template_resource("weapons/legacy_modules.py")

TEST: str = load_template_resource("weapons/test_auto_aim.py")
