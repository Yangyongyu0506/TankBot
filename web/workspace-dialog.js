// All editor entry points share one attempt gate; closing returns keyboard input to the game.
import {shortcut} from "./keyboard.js";

export function setupWorkspaceDialog(releaseControls){
  const dialog=document.getElementById("workspace-dialog"),toggle=document.getElementById("open-workspace");
  let editorFocus,locked=false,finished=false;
  function show(){
    if(locked)return;
    releaseControls();
    dialog.showModal();
    toggle.setAttribute("aria-expanded","true");
    const help=dialog.querySelector("#learning-pane:not([hidden]) #learning-title");
    const focus=innerWidth<1050&&help?help:editorFocus?.isConnected?editorFocus:dialog.querySelector(".cm-content");
    focus?.focus({preventScroll:true});
  }
  function hide(){if(dialog.open)dialog.close();}
  function lock(value){
    locked=value;toggle.disabled=value;
    toggle.title=value?"本次尝试运行中；请先结束本次尝试或重置关卡，再编辑代码。":"打开 / 收起代码编辑器";
    if(value)hide();
  }
  function end(){finished=true;lock(false);}
  toggle.addEventListener("click",()=>dialog.open?hide():show());
  document.getElementById("close-workspace").addEventListener("click",hide);
  dialog.addEventListener("beforetoggle",event=>{
    if(event.newState==="closed"&&dialog.contains(document.activeElement))editorFocus=document.activeElement;
  });
  dialog.addEventListener("close",()=>{
    toggle.setAttribute("aria-expanded","false");
    document.getElementById("arena").focus({preventScroll:true});
  });
  dialog.addEventListener("cancel",event=>{
    event.preventDefault();
    // Escape belongs to CodeMirror/Vim while editing.
    if(!document.activeElement?.closest(".cm-editor"))hide();
  });
  window.addEventListener("keydown",event=>{
    if(document.getElementById("settings-dialog")?.open||!shortcut(event,"editor"))return;
    event.preventDefault();event.stopImmediatePropagation();
    if(!event.repeat)(dialog.open?hide():show());
  },{capture:true});
  window.addEventListener("tankbot-deployment-status",({detail:status})=>{
    if(status.attempt_status&&status.attempt_status!=="active")end();
    // Activation arrives before the slower campaign poll. Preparing responses cannot undo this lock.
    else if(!finished&&status.attempt_status==="active"&&status.active)lock(true);
  });
  return {
    updateAttempt(attempt){
      if(!attempt)return;
      if(attempt.status!=="active")end();
      else if(!finished&&attempt.phase==="running")lock(true);
      // Restart/switch creates a new page and controller; terminal state cannot regress on stale polls.
    }
  };
}
