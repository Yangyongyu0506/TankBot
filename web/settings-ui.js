import {labels,controlKeys,setBindings,binding,shortcut,keyLabel,validCode} from "/keyboard.js";

export async function mountSettings(releaseControls,beforeReload){
  const $=id=>document.getElementById(id),dialog=$("settings-dialog");
  let state=await (await fetch("/api/settings")).json(),draft,recording=null,previousFocus;
  if(state.error||!state.settings)throw Error("无法读取设置");
  setBindings(state.settings.keyboard);
  function updateLabels(){
    $("open-workspace").querySelector("kbd").textContent=keyLabel(binding("editor"));
    $("toggle-learning").querySelector("kbd").textContent=keyLabel(binding("help"));
    $("settings-shortcut").textContent=keyLabel(binding("settings"));
    $("close-workspace").title="关闭代码编辑器（"+keyLabel(binding("editor"))+"）";
    $("close-learning").title="返回代码（"+keyLabel(binding("help"))+"）";
    $("workspace-shortcut").textContent="ROBOT WORKSPACE · "+keyLabel(binding("editor"))+" 打开 / 收起";
    for(const button of document.querySelectorAll("button[data-key]")){
      const canonical=button.dataset.key,action=Object.keys(controlKeys).find(name=>controlKeys[name]===canonical);
      if(action){button.textContent=keyLabel(binding(action));button.title=labels[action];}
    }
    $("fire").textContent=keyLabel(binding("fire"))+" · 单发";
    $("application-mode").textContent=state.settings.developer_mode?"开发者模式":"玩家模式";
    window.dispatchEvent(new Event("bindings-changed"));
  }
  function render(){
    $("developer-mode").checked=draft.developer_mode;
    $("keyboard-bindings").replaceChildren(...Object.entries(labels).map(([action,label])=>{
      const row=document.createElement("div"),text=document.createElement("span"),button=document.createElement("button");
      text.textContent=label;button.type="button";button.dataset.action=action;button.textContent=recording===action?"请按一个键…":keyLabel(draft.keyboard[action]);
      button.onclick=()=>{recording=action;$("settings-message").textContent="按下新的按键，Esc 取消；组合键暂不支持。";render();};
      row.append(text,button);return row;
    }));
    $("settings-path").textContent=state.settings_file;$("progress-path").textContent=state.progress_file;
  }
  function close(){recording=null;if(dialog.open)dialog.close();}
  function open(){
    if(dialog.open){close();return;}
    previousFocus=document.activeElement;releaseControls();draft=structuredClone(state.settings);recording=null;render();
    $("settings-message").textContent="修改后点击保存。模式切换会重新开始关卡，请先保存代码。";
    dialog.showModal();$("close-settings").focus();
  }
  $("open-settings").onclick=open;$("close-settings").onclick=close;
  dialog.addEventListener("cancel",e=>{e.preventDefault();if(recording){recording=null;render();}else close();});
  dialog.addEventListener("close",()=>{recording=null;(previousFocus?.isConnected?previousFocus:$("arena")).focus({preventScroll:true});});
  window.addEventListener("keydown",event=>{
    if(dialog.open&&recording){
      event.preventDefault();event.stopImmediatePropagation();
      if(event.code==="Escape"){recording=null;render();return;}
      if(!validCode(event.code)||event.ctrlKey||event.metaKey||event.altKey||event.shiftKey||event.isComposing){$("settings-message").textContent="请选择字母、数字、方向键、空格或 F1–F12，不使用组合键。";return;}
      const other=Object.keys(draft.keyboard).find(action=>action!==recording&&draft.keyboard[action]===event.code);
      if(other){$("settings-message").textContent="此按键已用于“"+labels[other]+"”，请先更换该操作的按键。";return;}
      draft.keyboard[recording]=event.code;recording=null;$("settings-message").textContent="键位已修改，保存后生效。";render();return;
    }
    if(shortcut(event,"settings")){
      event.preventDefault();event.stopImmediatePropagation();if(!event.repeat)open();
    }else if(dialog.open){event.stopImmediatePropagation();}
  },{capture:true});
  $("developer-mode").onchange=()=>{draft.developer_mode=$("developer-mode").checked;};
  $("reset-bindings").onclick=()=>{draft.keyboard=structuredClone(state.defaults.keyboard);recording=null;render();};
  async function save(value){
    const response=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":state.control_token},body:JSON.stringify({revision:state.revision,settings:value})});
    const result=await response.json();if(!response.ok)throw Error(result.error??"设置保存失败");
    state={...result,control_token:state.control_token};setBindings(state.settings.keyboard);updateLabels();return result;
  }
  $("save-settings").onclick=async()=>{
    const workspace=$("workspace-panel");
    if(draft.developer_mode!==state.settings.developer_mode&&(workspace.dataset.dirty==="true"||workspace.dataset.busy==="true"||workspace.dataset.runtimeBusy==="true")){
      $("settings-message").textContent="切换模式前请保存代码，并等待测试或部署完成。";return;
    }
    $("save-settings").disabled=true;
    try{releaseControls();const result=await save(draft);if(result.reload_required){beforeReload();location.reload();return;}close();}
    catch(error){$("settings-message").textContent=error.message;}
    finally{$("save-settings").disabled=false;}
  };
  updateLabels();
  // Another tab may have changed the mode. Revoke its old Worker and reload the UI.
  setInterval(async()=>{
    try{const current=await (await fetch("/api/settings")).json();
      if(current.settings.developer_mode!==state.settings.developer_mode){releaseControls();beforeReload();location.reload();}
    }catch{}
  },1500);
  return {get value(){return state.settings;},saveLayers:async layers=>{
    const result=await save({...state.settings,layers});return result.settings;
  }};
}
