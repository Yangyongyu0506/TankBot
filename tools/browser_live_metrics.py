#!/usr/bin/env python3
"""C2 live RMSE through the real player UI, using disposable files and saved progress."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.workspace import WorkspaceStore
from tankbot_host.application import ApplicationState
from campaign_support import solutions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-store',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:8795')
    parser.add_argument('--port',type=int,default=2832)
    parser.add_argument('--output',type=Path,default=ROOT/'.m1-cache/live-rmse/ui.json')
    args=parser.parse_args()
    args.output=args.output.resolve()
    if args.prepare_store:
        if (args.prepare_store/'HEAD.json').exists():raise SystemExit('Use a fresh disposable store')
        config=load_config(ROOT/'config/game.yaml')
        WorkspaceStore(args.prepare_store,solutions(configure(config,'c2')),config['workspace'])
        state=ApplicationState(config,args.prepare_store.parent/'settings.yaml',args.prepare_store.parent/'progress.json')
        for level in ('c0','c1'):state.complete(state.register_attempt(level),level)
        return
    b=Browser(args.port)
    def click(identifier):
        b.until("return document.getElementById('workspace-panel').dataset.busy==='false'&&!document.getElementById("+json.dumps(identifier)+").disabled;")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")
    def ready():b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=120)
    def state():
        b.script("window.__liveState=null;(async()=>{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__liveState=qa?JSON.parse(await qa.post('/api/campaign',{})).value:await(await fetch('/api/campaign')).json();})();return true;")
        return b.until('return window.__liveState;')
    def screenshot(name):
        path=args.output.parent/(args.output.stem+'-'+name+'.png')
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path.relative_to(ROOT))
    def reload_level(level):
        origin=b.script('return performance.timeOrigin;')
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";return true;")
        click('start-level')
        b.until('return performance.timeOrigin!=='+str(origin)+';');ready()
    try:
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':950});ready()
        assert b.script("return document.getElementById('application-mode').textContent;")=='玩家模式'
        if state()['attempt']['phase']!='preparing':reload_level('c2')
        assert b.script("return !document.getElementById('live-evaluation').hidden&&document.getElementById('live-evaluation').dataset.samples==='0';")
        click('open-workspace');click('test-workspace')
        report=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s.last;",timeout=120)
        assert report['status']=='Ready',report
        assert state()['attempt']['live_metrics']=={'rmse_m':None,'scored_samples':0}
        click('deploy-workspace')
        b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active';",timeout=120)
        b.until("return !document.getElementById('workspace-dialog').open;")
        b.until("return Number(document.getElementById('live-evaluation').dataset.samples)>=5;",timeout=30)
        assert '累计位置 RMSE' in b.script("return document.getElementById('editor-attempt-status').textContent;")
        running=state();assert running['attempt']['result'] is None
        b.until("return document.querySelector('#live-evaluation polyline').getAttribute('points').split(' ').length>=2;")
        hud=screenshot('running')
        layouts=[]
        for width,height in ((1280,800),(500,740)):
            b.call('WebDriver:SetWindowRect',{'width':width,'height':height})
            layouts.append(b.script("const root=document.getElementById('live-evaluation'),r=root.getBoundingClientRect(),d=document.scrollingElement;return {width:innerWidth,pageScroll:d.scrollWidth>d.clientWidth||d.scrollHeight>d.clientHeight,visible:r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};"))
        assert all(not row['pageScroll'] and row['visible'] for row in layouts),layouts
        b.call('WebDriver:SetWindowRect',{'width':1440,'height':950})
        click('finish-level');b.until("return document.getElementById('task-status').dataset.status==='ended';")
        finished=state();assert finished['attempt']['result']['rmse_m']==finished['attempt']['live_metrics']['rmse_m']
        reload_level('c2')
        assert b.script("return document.getElementById('live-evaluation').dataset.samples==='0'&&document.getElementById('live-evaluation').dataset.value==='';")
        reload_level('c1');assert b.script("return document.getElementById('live-evaluation').hidden;")
        args.output.write_text(json.dumps({'url':args.url,'browser':b.capabilities,'ordinary_player':True,'test':report,'running':running,
            'finished':finished,'editor_metric':True,'restart_clears_metric':True,'other_level_hidden':True,'layouts':layouts,'screenshot':hud},ensure_ascii=False,indent=2)+'\n')
        print(args.output)
    finally:b.close()


if __name__=='__main__':main()
