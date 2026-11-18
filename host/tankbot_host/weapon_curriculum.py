"""Reusable raw-observation and prediction scaffolds. No executable level plugins."""
from .template_resources import load_template_resource

ARMOR_TRACKER: str = load_template_resource("weapons/armor_tracker.py")

ARMOR_ADAPTER: str = load_template_resource("weapons/armor_module.py")

ARMOR_TEST: str = load_template_resource("weapons/test_armor_contract.py")

POLAR_TRACKER: str = load_template_resource("weapons/polar_tracker.py")

FUSION_TRACKER: str = load_template_resource("weapons/fusion_tracker.py")

TARGET_PREDICTION: str = load_template_resource("weapons/target_prediction.py")

POLAR_AUTO_AIM: str = load_template_resource("weapons/auto_aim.py")

RAW_ADAPTERS: str = load_template_resource("weapons/observations.py")

PREDICTIVE_ADAPTER: str = load_template_resource("weapons/aiming.py")

POLAR_TEST: str = load_template_resource("weapons/test_polar_contract.py")

FUSION_TEST: str = load_template_resource("weapons/test_fusion_contract.py")

PREDICTIVE_TEST: str = load_template_resource("weapons/test_prediction_contract.py")
