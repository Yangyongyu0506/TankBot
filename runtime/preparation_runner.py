"""One-shot player preparation, then the existing periodic runner in the same Worker."""
import contextlib
import importlib
from pathlib import Path
import sys
import traceback
import numpy as np
from tankbot.maps import OccupancyGrid, readonly_xy


def clear_project_modules(workspace):
    root = Path(workspace).resolve()
    for name, module in list(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if isinstance(filename, str) and Path(filename).resolve().is_relative_to(root):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


class PreparationRunner:
    def __init__(self, init):
        # Interpreter/dependency loading and project tests have completed. No
        # player planner, setup or reset is invoked before the timed request.
        self.init = init
        self.planned = self.initialized = False
        self.runner = None
        self.identity = None
        clear_project_modules(init['workspace'])

    def step(self, request):
        if request.get('preparation_version') != '1.0':
            if self.runner is None:
                raise ValueError('PREPARATION_REQUIRED: 周期模块尚未初始化')
            return self.runner.step(request)
        fields = ('preparation_version', 'request_id', 'run_id', 'deployment_id', 'task_id', 'operation')
        response = {key: request[key] for key in fields}
        if request['run_id'] != self.init['run_id']:
            raise ValueError('PREPARATION_IDENTITY')
        try:
            with contextlib.redirect_stdout(sys.stderr):
                if request['operation'] == 'plan':
                    if self.planned:
                        raise ValueError('PREPARATION_ALREADY_CALLED')
                    self.planned = True
                    self.identity = (request['run_id'], request['deployment_id'], request['task_id'])
                    clear_project_modules(self.init['workspace'])
                    sys.path.insert(0, self.init['workspace'])
                    p = request['payload']
                    m = p['map_data']
                    map_data = OccupancyGrid(np.asarray(m['grid'], dtype=np.bool_), np.array(m['origin_xy']), m['resolution_m'])
                    path, name = self.init['preparation']['entry_point'].split(':')
                    cls = getattr(importlib.import_module(path), name)
                    planner = cls(map_data, float(p['robot_radius_m']), float(p['safety_margin_m']))
                    result = planner.plan(readonly_xy(p['start_xy']), readonly_xy(p['goal_xy']))
                    if result is not None:
                        if not isinstance(result, np.ndarray) or result.dtype != np.float64:
                            raise TypeError('PLANNING_PATH_DTYPE: plan必须返回float64 NumPy数组或None')
                        if result.ndim != 2 or result.shape[1] != 2:
                            raise ValueError('PLANNING_PATH_SHAPE: plan必须返回(N,2)绝对map坐标')
                        if not 2 <= len(result) <= self.init['preparation_limits']['max_path_points']:
                            raise ValueError('PLANNING_PATH_CAPACITY: 规划点数超过合同或不足2')
                        if not np.isfinite(result).all():
                            raise ValueError('PLANNING_PATH_FINITE: 规划包含NaN/Inf')
                        result = {'dtype': 'float64', 'shape': list(result.shape), 'points_m': result.tolist()}
                    payload = {'status': 'completed', 'result': result}
                elif request['operation'] == 'initialize':
                    if not self.planned or self.initialized or self.identity != (request['run_id'], request['deployment_id'], request['task_id']):
                        raise ValueError('PREPARATION_IDENTITY_OR_PHASE')
                    self.initialized = True
                    clear_project_modules(self.init['workspace'])
                    reference = request['payload']['path']
                    self.init['config']['path_tracking_parameters']['reference'] = reference
                    from module_runner import ModuleRunner
                    self.runner = ModuleRunner(self.init)
                    payload = {'status': 'completed', 'result': None}
                else:
                    raise ValueError('PREPARATION_OPERATION')
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            payload = {'status': 'failed', 'result': None, 'error': type(error).__name__+': '+str(error)[:512]}
        return {**response, 'payload': payload}

    def close(self):
        if self.runner is not None:
            self.runner.close()
