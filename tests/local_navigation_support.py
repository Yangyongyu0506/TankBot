"""Local avoidance references installed only into temporary test projects."""
from pathlib import Path
from planning_support import solution as planning_solution

FIXTURES=Path(__file__).parent/'fixtures'


def solution(config,algorithm='geometric'):
    files=planning_solution(config)
    if algorithm not in ('geometric','dwa','nominal','stop'):raise ValueError(algorithm)
    if algorithm in ('geometric','dwa'):
        files['navigation/local_controller.py']=(FIXTURES/f'local_{algorithm}.py').read_text()
    else:
        output='observation.nominal_command' if algorithm=='nominal' else 'Twist()'
        files['navigation/local_controller.py']='from tankbot import Twist\nclass LocalController:\n def __init__(self,*args):pass\n def update(self,observation,dt):return '+output+'\n'
    return files
