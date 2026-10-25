"""Small registries for the existing progress checks, terminal rules and diagnostics."""
import math
import operator

COMPARISONS = {"==":operator.eq,"!=":operator.ne,"<":operator.lt,"<=":operator.le,">":operator.gt,">=":operator.ge}


def evaluate(rule, facts, parameters):
    kind = rule["type"]
    if kind == "compare":
        value=parameters[rule["parameter"]] if "parameter" in rule else rule["value"]
        return COMPARISONS[rule["operator"]](facts[rule["metric"]],value)
    if kind == "all":return all(evaluate(child,facts,parameters) for child in rule["conditions"])
    if kind == "any":return any(evaluate(child,facts,parameters) for child in rule["conditions"])
    if kind == "not":return not evaluate(rule["condition"],facts,parameters)
    raise ValueError("UNKNOWN_RULE_COMPONENT: "+kind)


PROGRESS = {
    "displacement":lambda pose,origin:math.hypot(pose[0]-origin[0],pose[1]-origin[1]),
    "heading_change":lambda pose,origin:abs((pose[2]-origin[2]+math.pi)%math.tau-math.pi),
}
METRICS = {
    "position_rmse":lambda point,truth:math.hypot(point["x_m"]-truth[0],point["y_m"]-truth[1]),
    "yaw_rmse":lambda point,truth:((point["yaw_rad"]-truth[2]+math.pi)%math.tau-math.pi) if "yaw_rad" in point else None,
}


class Diagnostics:
    def __init__(self, specification):
        self.metrics=specification["metrics"]
        self.squared={metric["id"]:0.0 for metric in self.metrics}
        self.counts={metric["id"]:0 for metric in self.metrics}

    def observe(self, point, truth):
        if truth is None:return
        for metric in self.metrics:
            error=METRICS[metric["type"]](point,truth)
            if error is not None:
                key=metric["id"];self.squared[key]+=error*error;self.counts[key]+=1

    def report(self):
        result={"rmse_m":None,"yaw_rmse_rad":None}
        for key,count in self.counts.items():
            value=math.sqrt(self.squared[key]/count) if count else None
            result[key]=value if value is None or math.isfinite(value) else None
        return result
