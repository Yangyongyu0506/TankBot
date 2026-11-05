#!/usr/bin/env python3
"""Real editor/lab/timing/storage acceptance. Use only with the isolated test_browser launcher."""
import argparse
import base64
import json
from pathlib import Path
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from browser_driver import Browser


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',required=True);parser.add_argument('--port',type=int,required=True);parser.add_argument('--mode',choices=('native','browser'),required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();browser=Browser(args.port);evidence={'mode':args.mode,'url':args.url}
    def script(code):return browser.script(code)
    def click(name):
        browser.until('return !!document.getElementById('+json.dumps(name)+')&&!document.getElementById('+json.dumps(name)+').disabled&&document.querySelector("dialog[open]")?.dataset.busy!=="true";',90)
        script('document.getElementById('+json.dumps(name)+').click();return true;')
    def request(path,value=None,runtime=False):
        token="(await(await fetch('/api/workspace')).json()).control_token"
        if runtime and args.mode=='browser':expression="JSON.parse(await(window.wrappedJSObject?.tankbotQA??window.tankbotQA).post("+json.dumps(path)+','+json.dumps(value or {})+")).value"
        else:expression="await(await fetch("+json.dumps(path)+( ",{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':"+token+"},body:JSON.stringify("+json.dumps(value)+")}" if value is not None else '')+")).json()"
        script("window.__engineeringReply=null;(async()=>{try{window.__engineeringReply={value:"+expression+"};}catch(e){window.__engineeringReply={error:String(e)};}})();return true;")
        result=browser.until('return window.__engineeringReply;',120)
        if 'error' in result:raise AssertionError(result['error'])
        value=result['value']
        if isinstance(value,dict) and 'error' in value:raise AssertionError(value['error'])
        return value
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def lab():return request('/api/experiment/status',{},True)
    def wait_reports(count):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            value=lab()
            if not value['job'] and len(value['comparisons'])==count:return value
            time.sleep(.25)
        raise AssertionError('Lab comparison did not finish')
    def shot(name):
        path=args.output.with_name(name+'.png');path.write_bytes(base64.b64decode(browser.call('WebDriver:TakeScreenshot',{})['value']));return str(path)
    try:
        browser.navigate(args.url);browser.call('WebDriver:SetWindowRect',{'width':1500,'height':1050});ready()
        initial=request('/api/workspace')['snapshot'];click('open-workspace');click('test-workspace')
        browser.until("return !document.getElementById('deploy-workspace').disabled;",120);click('deploy-workspace')
        browser.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",120)
        click('open-experiment');browser.until("return document.getElementById('experiment-version-a').options.length>=2;",60)
        click('experiment-start');browser.until("return document.getElementById('experiment-record').textContent.includes('录制中');")
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            current=lab()
            if current['frames']>=35:break
            time.sleep(.2)
        assert current['frames']>=20,current
        click('experiment-stop');click('experiment-end-attempt')
        browser.until("return !document.getElementById('experiment-stop').disabled===false;")
        click('experiment-compare');compared=wait_reports(2)
        browser.until("return document.getElementById('experiment-results').dataset.completed==='2';",30)
        reports=compared['comparisons']
        evidence['comparison_attempts']=[{k:r[k] for k in ('revision','status','scored_samples','failure','timing','logs')} for r in reports]
        # A real host wall-deadline is a valid, visible experiment outcome, not
        # an algorithm pass. Do not retry it away or widen the execution budget.
        assert reports[0]['status']=='Completed',reports[0]['failure']
        for report in reports:
            assert report['status']=='Completed' or (report['status']=='Failed'
                and report['failure']['code'] in ('RESOURCE_LIMIT','MISSED_DEADLINE')
                and report['timing']['timeouts']>0),report['failure']
        evidence['both_versions_completed']=all(r['status']=='Completed' for r in reports)
        assert reports[0]['revision']!=reports[1]['revision']
        assert reports[0]['input_sha256']==reports[1]['input_sha256']
        assert reports[0]['scored_samples']>0 and reports[1]['scored_samples']>0
        assert any(p['estimate'] and p['estimate'].get('covariance') for p in reports[0]['points'])
        assert any(p['diagnostics'] for p in reports[0]['points'])
        evidence['comparison']=[{k:r[k] for k in ('revision','rmse_m','scored_samples','input_sha256','status')} for r in reports]
        evidence['lab_screenshot']=shot('lab-comparison')
        click('experiment-save');browser.until("return document.getElementById('experiment-saved').options.length>0;")
        package=request('/api/experiment/export',{},True)
        assert not package['evaluation_reference_exported'] and 'references' not in package
        evidence['record_metadata']={k:package['record'][k] for k in ('seed','recording_start_tick','deployment_tick','configuration_sha256','environment')}
        assert package['record']['environment']['runtime_packages'].get('numpy')
        runtime=request('/api/deployment',{},True) if args.mode=='browser' else request('/api/deployment')
        timing=runtime['timing'];assert timing['backend']==('native' if args.mode=='native' else 'pyodide')
        assert timing['costs']['round_trip_ms']['count']>0 and timing['modules']['perception']['update_ms']['count']>0
        assert timing['budget_ms']==20
        evidence['timing']=timing
        healthy=reports[0]['revision']
        click('close-experiment');click('open-workspace')
        script("[...document.querySelectorAll('#file-list button')].find(n=>n.title==='perception/tracker.py').click();const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,'class Tracker:\\n    def update(self, measurements, dt):\\n        raise ValueError(\"engineering-filter-debug\")\\n');return true;")
        click('save-workspace');browser.until("return document.getElementById('workspace-panel').dataset.dirty==='false';")
        bad=request('/api/workspace')['snapshot'];click('close-workspace');click('open-experiment')
        browser.until('return [...document.getElementById("experiment-version-a").options].some(o=>o.value==='+json.dumps(bad['revision'])+');')
        script("document.getElementById('experiment-version-a').value="+json.dumps(bad['revision'])+";document.getElementById('experiment-version-b').value="+json.dumps(healthy)+";return true;")
        click('experiment-compare');failed=wait_reports(2)
        assert failed['comparisons'][0]['status']=='Failed',failed
        evidence['exception_failure']={k:failed['comparisons'][0][k] for k in ('revision','failure','logs','timing')}
        browser.until("return document.querySelector('.experiment-error')?.textContent.includes('engineering-filter-debug');",30)
        evidence['failure_screenshot']=shot('lab-failure');click('experiment-save')
        browser.until("return document.getElementById('experiment-saved').options.length>=2;")
        click('experiment-load');browser.until("return document.getElementById('experiment-record').textContent.includes('无私有评分参考');")
        assert not lab()['private_scoring_available']
        click('close-experiment');click('tab-logs');script("document.getElementById('runtime-timing').open=true;return true;")
        browser.until("return document.getElementById('runtime-timing-content').textContent.includes('p99');")
        evidence['timing_screenshot']=shot('runtime-timing')
        backup=request('/api/workspace/backup_export',{})
        head=request('/api/workspace')['snapshot']['revision'];drafts=[]
        for index in range(3):
            head=request('/api/workspace/save',{'revision':head,'changes':{'experiment_notes.py':f'VALUE: int = {index}\n'}})['revision'];drafts.append(head)
        browser.navigate(args.url);ready();click('open-workspace');click('open-storage')
        browser.until("return document.getElementById('storage-dialog').dataset.totalBytes;")
        inventory=request('/api/workspace/storage',{});assert inventory['categories']['experiments']['count']>=2
        pin=drafts[0];script("document.querySelector('#storage-versions input[data-revision=\""+pin+"\"]').click();return true;")
        browser.until("return document.querySelector('#storage-versions input[data-revision=\""+pin+"\"]').checked;")
        script("document.getElementById('storage-keep').value='0';return true;");click('storage-plan')
        preview=browser.until("const t=document.getElementById('storage-preview').textContent;return t.startsWith('{')&&JSON.parse(t);",60)
        assert pin+'.json' not in preview['files'] and drafts[1]+'.json' in preview['files'],preview
        assert request('/api/workspace')['snapshot']['revision']==head
        click('storage-apply');browser.until("return document.getElementById('storage-recovery').textContent.includes('complete');",60)
        inventory=request('/api/workspace/storage',{});recovery=next(r for r in inventory['recovery'] if r['state']=='complete')
        script("[...document.querySelectorAll('#storage-recovery button')].find(n=>n.textContent==='恢复历史').click();return true;")
        browser.until("return document.getElementById('storage-recovery').textContent.includes('restored');",60)
        assert request('/api/workspace/revision',{'revision':drafts[1]})['revision']==drafts[1]
        script("document.querySelector('#storage-backups input[data-backup=\""+backup['sha256']+"\"]').click();return true;")
        click('storage-plan-backups');browser.until("return document.getElementById('storage-preview').textContent.includes('backup_cleanup');")
        click('storage-apply');browser.until("return document.getElementById('storage-apply').hidden;")
        assert 'backup-'+backup['sha256']+'.json.gz' not in request('/api/workspace/storage',{})['backups']
        script("const f=new File([JSON.stringify("+json.dumps(backup)+")],'project.json',{type:'application/json'}),d=new DataTransfer();d.items.add(f);const i=document.getElementById('storage-import');i.files=d.files;i.dispatchEvent(new Event('change',{bubbles:true}));return true;")
        browser.until("return document.getElementById('storage-preview').textContent.includes('incoming_revision');",60)
        evidence['storage_screenshot']=shot('workspace-storage')
        origin=script('return performance.timeOrigin;');click('storage-apply');browser.until('return performance.timeOrigin!=='+str(origin)+';',60);ready()
        restored=request('/api/workspace')['snapshot'];assert restored['revision']==backup['head_revision']
        assert request('/api/workspace/revision',{'revision':head})['revision']==head
        assert restored['files']['perception/transforms.py']==initial['files']['perception/transforms.py']
        progress=request('/api/progress');assert progress['completed_levels']==['c0','c1'] and not progress['developer_mode']
        assert script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
        # Diagnose an actual update that never returns, using the unchanged host deadline.
        timeout=request('/api/workspace/save',{'revision':restored['revision'],'changes':{
            'perception/tracker.py':'class Tracker:\n    def update(self, measurements, dt):\n        while True:\n            pass\n'}})
        snapshot=request('/api/workspace/revision',{'revision':timeout['revision']})
        # Browser refresh creates a new Authority; explicitly restore public input,
        # never resurrect the old private evaluator sidecar across reloads.
        request('/api/experiment/import',{'record':package['record']},True)
        request('/api/experiment/clear',{},True)
        request('/api/experiment/compare',{'snapshot':snapshot} if args.mode=='browser' else {'revision':snapshot['revision']},True)
        timeout_report=wait_reports(1)['comparisons'][0]
        assert timeout_report['status']=='Failed' and timeout_report['failure']['code'] in ('RESOURCE_LIMIT','MISSED_DEADLINE'),timeout_report['failure']
        assert timeout_report['timing']['timeouts']==1
        assert timeout_report['timing']['recent'][-1]['failure_location'] in ('wall_deadline','commit_gate')
        evidence['wall_deadline_failure']={k:timeout_report[k] for k in ('revision','failure','timing')}
        back=request('/api/workspace/save',{'revision':timeout['revision'],'changes':{
            'perception/tracker.py':restored['files']['perception/tracker.py']}})
        assert back['revision']==restored['revision']
        evidence.update(passed=True,private_reference_not_exported=True,failed_version_traceback=True,backup_restore=True,
                        interrupted_storage_covered_by_python=True,old_sources_and_progress_preserved=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: '+args.mode+' real editor/deploy, same-input A/B, covariance/diagnostics, traceback, timing, storage preview/recovery/restore')
    except BaseException as error:
        evidence['error']=str(error)[:6000];evidence['failure_screenshot']=shot('failure');args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');raise
    finally:browser.close()


if __name__=='__main__':main()
