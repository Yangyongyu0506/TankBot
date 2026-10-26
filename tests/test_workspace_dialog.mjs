import test from 'node:test';
import assert from 'node:assert/strict';
import {setBindings} from '../web/keyboard.js';
import {setupWorkspaceDialog} from '../web/workspace-dialog.js';

function fixture(){
  const dispatch=(target,type,properties={})=>{
    const event=new Event(type,{cancelable:true});Object.assign(event,properties);target.dispatchEvent(event);return event;
  };
  class Element extends EventTarget{
    disabled=false;open=false;isConnected=true;attributes={};
    focus(){document.activeElement=this;}
    setAttribute(name,value){this.attributes[name]=value;}
    click(){if(!this.disabled)dispatch(this,'click');}
  }
  const elements=Object.fromEntries(['workspace-dialog','open-workspace','close-workspace','settings-dialog','arena','editor'].map(id=>[id,new Element()]));
  globalThis.window=new EventTarget();
  globalThis.document={getElementById:id=>elements[id],activeElement:elements['open-workspace']};
  globalThis.innerWidth=1280;
  const dialog=elements['workspace-dialog'],editor=elements.editor;
  dialog.querySelector=selector=>selector==='.cm-content'?editor:null;
  dialog.contains=element=>element===editor;
  dialog.showModal=()=>{dialog.open=true;};
  dialog.close=()=>{if(dialog.open){dispatch(dialog,'beforetoggle',{newState:'closed'});dialog.open=false;dispatch(dialog,'close');}};
  let releases=0;
  setBindings({editor:'F2'});
  const controller=setupWorkspaceDialog(()=>releases++);
  return {...elements,controller,dispatch,keydown:code=>dispatch(window,'keydown',{code}),
    deployment:detail=>dispatch(window,'tankbot-deployment-status',{detail}),releases:()=>releases};
}

test('closing the editor returns focus to the game, preserving editor focus for reopening',()=>{
  const f=fixture();f['open-workspace'].click();assert.equal(f['workspace-dialog'].open,true);
  assert.equal(document.activeElement,f.editor);f['close-workspace'].click();
  assert.equal(document.activeElement,f.arena);assert.equal(f['open-workspace'].attributes['aria-expanded'],'false');
  f.keydown('F2');assert.equal(document.activeElement,f.editor);assert.equal(f.releases(),2);
});

test('successful deployment closes and locks every normal editor entry until the attempt ends',()=>{
  const f=fixture();f['open-workspace'].click();
  f.deployment({attempt_status:'active',active:{deployment_id:'candidate'}});
  assert.equal(f['workspace-dialog'].open,false);assert.equal(f['open-workspace'].disabled,true);
  assert.equal(document.activeElement,f.arena);
  f['open-workspace'].click();f.keydown('F2');f.dispatch(f['open-workspace'],'click');
  assert.equal(f['workspace-dialog'].open,false);assert.equal(f.releases(),1);
  f.controller.updateAttempt({status:'active',phase:'preparing'});
  assert.equal(f['open-workspace'].disabled,true,'stale preparing poll unlocked running attempt');
  f.deployment({attempt_status:'active',active:{deployment_id:'candidate'},runtime_fault:'MODULE_ERROR'});
  assert.equal(f['open-workspace'].disabled,true,'runtime failure must not end the attempt');
  f.controller.updateAttempt({status:'ended',phase:'finished'});
  assert.equal(f['open-workspace'].disabled,false);f.keydown('F2');assert.equal(f['workspace-dialog'].open,true);
});

test('the campaign lifecycle also locks manual-control attempts and terminal state ignores stale running polls',()=>{
  const f=fixture();f['open-workspace'].click();
  f.controller.updateAttempt({status:'active',phase:'running'});assert.equal(f['workspace-dialog'].open,false);
  f.deployment({attempt_status:'passed',active:{deployment_id:'old'}});
  f.controller.updateAttempt({status:'active',phase:'running'});
  f.deployment({attempt_status:'active',active:{deployment_id:'old'}});
  assert.equal(f['open-workspace'].disabled,false);f['open-workspace'].click();assert.equal(f['workspace-dialog'].open,true);
});

test('tests, failed startup and free simulations do not lock editing',()=>{
  for(const status of [
    {attempt_status:'active',active:null,last:{status:'Ready'}},
    {attempt_status:'active',active:null,last:{status:'Failed'}},
    {attempt_status:null,active:{deployment_id:'sandbox'}}
  ]){
    const f=fixture();f['open-workspace'].click();f.deployment(status);
    assert.equal(f['workspace-dialog'].open,true);assert.equal(f['open-workspace'].disabled,false);
  }
});
