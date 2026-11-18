"""Reusable wheel-controller scaffolding; no executable code is read from level YAML."""
from .template_resources import load_template_resource

CONTROLLER: str = load_template_resource("navigation/wheel_controller.py")

ADAPTER: str = load_template_resource("navigation/navigation_robot.py")

ODOMETRY: str = load_template_resource("navigation/odometry.py")

ODOMETRY_ADAPTER: str = load_template_resource("navigation/odometry_module.py")

EKF: str = load_template_resource("navigation/ekf.py")

EKF_ADAPTER: str = load_template_resource("navigation/ekf_module.py")

WAYPOINT_CONTROLLER = load_template_resource("navigation/waypoint_controller.py")
WAYPOINT_ADAPTER = load_template_resource("navigation/waypoint_module.py")
PATH_FOLLOWER = load_template_resource("navigation/path_follower.py")
PATH_ADAPTER = load_template_resource("navigation/path_module.py")
