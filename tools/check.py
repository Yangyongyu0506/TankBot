#!/usr/bin/env python3
"""本地和CI的检查入口；构建产物测试、真实浏览器流程明确分组。"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('standard','frontend','python','wasm','browser'),default='standard')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    extra=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    if extra and args.suite!='browser':parser.error('Only --suite browser accepts forwarded arguments')
    if args.suite in ('standard','python'):
        from python_env import relaunch_if_needed
        relaunch_if_needed(Path(__file__).resolve(),offline=args.offline)
    commands={
        'frontend':[['node','tools/test_frontend.mjs']],
        'python':[[sys.executable,'-m','unittest','discover','-s','tests','-v']],
        'wasm':[['node','tools/test_frontend.mjs','--wasm']],
        'browser':[[sys.executable,'tools/test_browser.py',*(['--offline'] if args.offline else []),*extra]],
    }
    standard=[*commands['frontend'],*commands['python'],['cargo','test','--locked'],
              [sys.executable,'docs/tools/check_design.py'],[sys.executable,'tools/export_profile.py','--check']]
    env=os.environ.copy()
    for command in standard if args.suite=='standard' else commands[args.suite]:
        if command[0]=='cargo':
            from build import cargo_tool
            command[0]=cargo_tool(ROOT,env)
            if args.offline:command.append('--offline')
        if 'tools/export_profile.py' in command and args.offline:command.append('--offline')
        print('CHECK: '+' '.join(command),flush=True)
        result=subprocess.run(command,cwd=ROOT,env=env)
        if result.returncode:return result.returncode if result.returncode>0 else 1
    return 0


if __name__=='__main__':raise SystemExit(main())
