#!/usr/bin/env python3
"""Real map preview probe; run against an isolated --map open_large developer session."""
import argparse
import base64
import json
from pathlib import Path
from browser_driver import Browser


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True)
    parser.add_argument('--browser-port',type=int,default=2834);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();b=Browser(args.browser_port);report={}
    def press(code):
        b.script(f"document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{{code:{json.dumps(code)},bubbles:true}}));return true;")
    def screenshot(name):
        path=args.output.with_name(args.output.stem+'-'+name+'.png')
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']));return str(path)
    try:
        b.navigate(args.url)
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
        b.until("return !document.getElementById('map-practice-note').hidden;",30)
        b.call('WebDriver:SetWindowRect',{'width':1280,'height':900})
        b.script("document.getElementById('open-map').click();return true;")
        b.until("return document.getElementById('map-select').options.length===6;",30)
        assert b.script("return document.getElementById('map-preview').dataset.wallCount==='4'&&document.getElementById('map-size').textContent.includes('20.40');")
        for code in ('KeyW','KeyJ','Space','F2','F1','F10'):press(code)
        assert b.script("return document.getElementById('map-dialog').open&&!document.getElementById('workspace-dialog').open&&!document.getElementById('settings-dialog').open&&!document.querySelector('button[data-key].active');")
        b.script("const s=document.getElementById('map-select');s.value='maps/navigation_warehouse.yaml';s.dispatchEvent(new Event('change'));return true;")
        assert b.script("return document.getElementById('map-preview').dataset.wallCount==='10'&&document.getElementById('map-launch-command').textContent.includes('--map');")
        report['desktop_screenshot']=screenshot('desktop')
        report['layouts']=[]
        for width,height in ((1280,900),(390,740)):
            b.call('WebDriver:SetWindowRect',{'width':width,'height':height})
            layout=b.script("const r=document.getElementById('map-dialog').getBoundingClientRect(),c=document.getElementById('map-preview').getBoundingClientRect();return {width:innerWidth,height:innerHeight,pageWidth:document.scrollingElement.scrollWidth,pageHeight:document.scrollingElement.scrollHeight,left:r.left,top:r.top,right:r.right,bottom:r.bottom,canvasHeight:c.height};")
            assert layout['pageWidth']<=layout['width'] and layout['pageHeight']<=layout['height'],layout
            assert layout['left']>=0 and layout['top']>=0 and layout['right']<=layout['width'] and layout['bottom']<=layout['height'],layout
            assert layout['canvasHeight']>0,layout
            report['layouts'].append(layout)
        report['mobile_screenshot']=screenshot('mobile')
        assert b.script("return document.getElementById('map-select').value==='maps/navigation_warehouse.yaml';")
        b.script("document.getElementById('close-map').click();return true;")
        assert b.script("return !document.getElementById('map-dialog').open&&document.activeElement.id==='arena';")
        # Previewing warehouse must not replace the running open_large map.
        b.script("window.__maps=null;fetch('/api/maps').then(r=>r.json()).then(v=>window.__maps=v);return true;")
        current=b.until('return window.__maps;')
        assert current['overridden'] and len(current['current']['walls'])==4
        b.call('WebDriver:SetWindowRect',{'width':1280,'height':900})
        report['arena_screenshot']=screenshot('arena')
        b.script("document.getElementById('start-level').click();return true;")
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&!document.getElementById('map-practice-note').hidden;",120)
        b.script("document.getElementById('open-map').click();return true;")
        b.until("return document.getElementById('map-size').textContent.includes('20.40');",30)
        report.update(runtime='browser' if 'runtime=browser' in args.url else 'native',override_rendered=True,preview_read_only=True,controls_isolated=True,retry_preserved=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:b.close()


if __name__=='__main__':main()
