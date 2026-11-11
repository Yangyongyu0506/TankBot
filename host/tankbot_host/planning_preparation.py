"""Trusted deployment preparation controller; no player code executes in this module."""
import copy
import uuid
from .global_planning import validate_planned_path, PlanningError


class PlanningPreparation:
    def __init__(self, authority, job):
        self.authority, self.job = authority, job
        self.task = copy.deepcopy(authority.campaign.navigation.task)
        self.spec = authority.campaign.navigation.spec
        self.request = None
        self.phase = 'Planning'
        self.reference = None
        self.elapsed_ms = None
        self.python_ms = None
        self.done = False

    def submit(self, operation, payload):
        a, job = self.authority, self.job
        self.request = {'preparation_version': '1.0', 'request_id': uuid.uuid4().hex,
                        'run_id': a.run_id, 'deployment_id': job['id'], 'task_id': self.task['task_id'],
                        'operation': operation, 'payload': payload}
        a.validator.structure(self.request, 'preparation-task.schema.json')
        if not job['worker'].submit_preparation(self.request):
            raise PlanningError('PLANNING_SUBMIT_FAILED')
        a.logs.append(('规划（独立5秒墙钟，含导入/构造/搜索/后处理/往返）…\n' if operation == 'plan' else '规划路径已通过Authority校验；初始化周期控制模块…\n'),
                      source=job['kind'], module_id='global_planner', tick=a.tick, stream='status',
                      deployment_id=job['id'], revision=job['artifact']['revision'])

    def advance(self):
        a, job = self.authority, self.job
        if self.done:
            return True
        if self.request is None:
            self.submit('plan', {**{k: copy.deepcopy(self.task[k]) for k in ('start_xy', 'goal_xy', 'robot_radius_m', 'safety_margin_m')},
                                 'map_data': copy.deepcopy(self.task['map'])})
        else:
            result = job['worker'].poll_preparation()
            if job['worker'].fault:
                raise PlanningError('PLANNING_TIMEOUT' if job['worker'].fault == 'RESOURCE_LIMIT' else 'PLANNING_RUNTIME_ERROR')
            if result is None:
                return False
            if self.phase == 'Planning':
                self.elapsed_ms = job['worker'].task_elapsed_ms
            a.validator.structure(result, 'preparation-task.schema.json')
            if any(result[k] != self.request[k] for k in ('request_id', 'run_id', 'deployment_id', 'task_id', 'operation')):
                raise PlanningError('PLANNING_RESPONSE_IDENTITY: 拒绝旧/错误准备响应')
            if result['payload']['status'] != 'completed':
                raise PlanningError('PLANNING_ERROR: '+result['payload'].get('error', '规划或模块初始化失败'))
            if self.phase == 'Planning':
                self.python_ms=result['payload'].get('telemetry',{}).get('transport',{}).get('runtime_python_ms')
                self.reference = validate_planned_path(result['payload']['result'], self.task, self.spec)
                a.logs.append(f"完整规划往返墙钟 {self.elapsed_ms:.3f} ms；路径 {len(self.reference['points_m'])} 点、{self.reference['length_m']:.3f} m；安全校验通过。\n",
                              source=job['kind'],module_id='global_planner',tick=a.tick,stream='status',
                              deployment_id=job['id'],revision=job['artifact']['revision'])
                self.phase = 'Initializing'
                self.submit('initialize', {'path': self.reference})
            else:
                self.phase = 'Prepared'
                self.done = True
        job['phase'] = self.phase
        if job['kind'] != 'test':
            a.campaign.navigation.preparation = {'phase': self.phase.lower(), 'planning_elapsed_ms': self.elapsed_ms}
        return self.done

    def public(self):
        return {'task_id': self.task['task_id'], 'phase': self.phase,
                'wall_deadline_ms':self.job['init']['preparation']['wall_deadline_ms'],
                'planning_elapsed_ms': self.elapsed_ms, 'planning_python_ms': self.python_ms,
                'path_id': self.reference['path_id'] if self.reference else None,
                'path_points': len(self.reference['points_m']) if self.reference else None}
