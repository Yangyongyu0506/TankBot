#!/usr/bin/env python3
"""Real UI probe: viewport fit, modal toggles, focus isolation and unsaved draft retention."""
import argparse
import base64
import json
from pathlib import Path
from browser_driver import Browser


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8765')
    args=parser.parse_args();b=Browser()
    def press(code,key=None):
        b.script("const target=document.activeElement;target.dispatchEvent(new KeyboardEvent('keydown',{key:"+json.dumps(key or code)+",code:"+json.dumps(code)+",bubbles:true}));target.dispatchEvent(new KeyboardEvent('keyup',{key:"+json.dumps(key or code)+",code:"+json.dumps(code)+",bubbles:true}));return true;")
    def opened(): return b.script("return document.getElementById('workspace-dialog').open;")
    def layout():
        return b.script("const d=document.getElementById('workspace-dialog'),r=d.getBoundingClientRect(),c=document.getElementById('arena').getBoundingClientRect();return {width:innerWidth,height:innerHeight,pageWidth:document.scrollingElement.scrollWidth,pageHeight:document.scrollingElement.scrollHeight,scrollY:scrollY,open:d.open,dialog:{left:r.left,top:r.top,right:r.right,bottom:r.bottom},canvasHeight:c.height,editorHeight:document.getElementById('code-editor').getBoundingClientRect().height};")
    def fits(value):
        assert value['pageWidth']<=value['width'] and value['pageHeight']<=value['height'],value
        assert value['scrollY']==0 and value['canvasHeight']>0,value
        if value['open']:
            r=value['dialog'];assert r['left']>=0 and r['top']>=0 and r['right']<=value['width'] and r['bottom']<=value['height'],value
            assert value['editorHeight']>=80,value
    try:
        b.navigate(args.url)
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';")
        assert not opened()
        layouts=[]
        for width,height in ((1440,900),(1280,720),(1024,600),(390,740)):
            b.call('WebDriver:SetWindowRect',{'width':width,'height':height})
            b.until('return document.getElementById("arena").getBoundingClientRect().height>0;')
            closed=layout();fits(closed)
            press('F2');assert opened();visible=layout();fits(visible)
            b.script("document.getElementById('close-workspace').click();return true;");assert not opened()
            layouts.append({'closed':closed,'open':visible})
        b.call('WebDriver:SetWindowRect',{'width':1280,'height':800})
        # Opening releases a previously held movement key.
        b.script("document.getElementById('arena').focus();window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW',bubbles:true}));return true;")
        assert b.script("return document.querySelector('[data-key=KeyW]').classList.contains('active');")
        press('F2');assert opened()
        assert not b.script("return Boolean(document.querySelector('button[data-key].active'));")
        # Read only the authorized user's source, and keep edits in memory (never save/deploy).
        b.script("window.__dialogSeed=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__dialogSeed=v.snapshot);return true;")
        seed=b.until('return window.__dialogSeed;')
        path=b.script("return document.getElementById('editor-path').textContent;")
        source=seed['files'][path]
        draft=source+'\n# Unsaved dialog draft\n'
        b.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(draft)+");return true;")
        b.until("return !document.getElementById('save-workspace').disabled;")
        press('F2');assert not opened()
        press('F2');assert opened()
        assert b.script("return document.querySelector('.cm-content').textContent.includes('Unsaved dialog draft')&&document.getElementById('workspace-revision').textContent.includes('未保存');")
        assert b.script("return document.getElementById('editor-path').textContent;")==path
        press('Escape');assert opened(),'Escape must remain available to Vim/CodeMirror'
        # Background focus and even bubbled game hotkeys remain blocked while modal.
        focus=b.script("document.getElementById('arena').focus();return document.getElementById('workspace-dialog').contains(document.activeElement);")
        assert focus,'Modal focus escaped to the game'
        for code in ('KeyW','KeyJ','KeyL','Space'):press(code,' ' if code=='Space' else code[-1].lower())
        assert not b.script("return Boolean(document.querySelector('button[data-key].active'));")
        b.script("document.querySelector('.cm-content').focus();return true;")
        # Restore original source in memory, so leaving the probe doesn't trigger beforeunload.
        b.script("document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        b.until("return document.getElementById('save-workspace').disabled;")
        for name,visible in (('dialog-open',True),('dialog-game',False)):
            if opened()!=visible:press('F2')
            raw=b.call('WebDriver:TakeScreenshot',{})['value'];Path('.m1-cache',name+'.png').write_bytes(base64.b64decode(raw))
        b.script("document.getElementById('open-workspace').click();return true;");assert opened()
        b.script("document.getElementById('close-workspace').click();return true;");assert not opened()
        b.script("document.getElementById('tab-sensors').click();return true;")
        assert b.script("return !document.getElementById('hud-sensors').hidden&&document.getElementById('hud-chassis').hidden;")
        report={'layouts':layouts,'f2_toggle':True,'button_and_close':True,'unsaved_draft_preserved':True,'modal_focus':True,'escape_keeps_editor':True,'held_key_released':True,'game_keys_blocked':True,'hud_tabs':True}
        Path('.m1-cache/dialog-report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PASS: modal toggle, draft retention, focus/control isolation, HUD tabs; four viewport sizes fit without page scroll.')
    finally:b.close()


if __name__=='__main__':main()
