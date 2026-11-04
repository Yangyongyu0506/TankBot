// Presentation of the public catalogue. Access decisions remain in ApplicationState.
export function levelGraph(levels,chapters=[]){
  const ordered=levels.map((level,index)=>({...level,prerequisites:level.prerequisites??[],order:level.order??index})).sort((a,b)=>a.order-b.order);
  const byId=new Map(ordered.map(level=>[level.level_id,level]));
  if(byId.size!==ordered.length)throw Error("关卡目录含重复 ID");
  for(const level of ordered)for(const parent of level.prerequisites)if(!byId.has(parent))throw Error("关卡目录含未知前置："+parent);
  const depths=new Map(),pending=new Set(byId.keys());
  while(pending.size){
    const ready=ordered.filter(level=>pending.has(level.level_id)&&level.prerequisites.every(id=>depths.has(id)));
    if(!ready.length)throw Error("关卡目录含循环前置");
    for(const level of ready){depths.set(level.level_id,Math.max(-1,...level.prerequisites.map(id=>depths.get(id)))+1);pending.delete(level.level_id);}
  }
  const roots=ordered.filter(level=>!level.prerequisites.length),groups=new Map();
  for(const level of ordered.filter(level=>level.prerequisites.length)){
    const chapter=chapters.find(chapter=>chapter.chapter_id===level.chapter_id);
    if(!groups.has(level.chapter_id))groups.set(level.chapter_id,{id:level.chapter_id,title:chapter?.title??level.chapter_id??"学习主线",levels:[]});
    groups.get(level.chapter_id).levels.push(level);
  }
  for(const lane of groups.values())lane.levels.sort((a,b)=>depths.get(a.level_id)-depths.get(b.level_id)||a.order-b.order);
  return {levels:ordered,byId,depths,roots,lanes:[...groups.values()],edges:ordered.flatMap(level=>level.prerequisites.map(from=>({from,to:level.level_id})))};
}

export function levelState(level,progress,current){
  const done=new Set(progress?.completed_levels??[]),available=new Set(progress?.unlocked_levels??[]);
  const missing=level.prerequisites.filter(id=>!done.has(id));
  return {status:done.has(level.level_id)?"completed":progress?.developer_mode||available.has(level.level_id)?"available":"locked",
          current:level.level_id===current,missing};
}

export function newlyUnlocked(before,after,finished,{practice=false}={}){
  if(!before||practice||after.developer_mode||before.completed_levels.includes(finished)||!after.completed_levels.includes(finished))return [];
  const previously=new Set(before.unlocked_levels);
  return after.unlocked_levels.filter(id=>!previously.has(id));
}

export function mountLevelTree(profile,{releaseControls,onStart}){
  const $=id=>document.getElementById(id),dialog=$("level-tree-dialog"),stage=$("level-tree-stage"),svg=$("level-tree-edges");
  const graph=levelGraph(profile.campaign.levels,profile.campaign.chapters),current=profile.campaign.active_level;
  const buttons=new Map(),labels={completed:"已通关",available:"可挑战",locked:"未解锁"};
  let progress=null,selected=current??graph.roots[0]?.level_id,starting=false,opener=null,signature="";
  stage.style.gridTemplateColumns=`repeat(${Math.max(1,graph.lanes.length)},minmax(210px,1fr))`;
  function choose(id){selected=id;renderDetails();for(const [key,button] of buttons)button.setAttribute("aria-pressed",String(key===id));}
  function node(level){
    const item=document.createElement("li"),button=document.createElement("button"),code=document.createElement("span"),title=document.createElement("strong"),status=document.createElement("span");
    item.className="level-node-item";button.type="button";button.className="level-node";button.dataset.levelId=level.level_id;
    code.className="level-node-id";code.textContent=level.prerequisites.length?level.level_id:"公共入门 · "+level.level_id;
    title.textContent=level.title;status.className="level-node-status";button.append(code,title,status);item.append(button);
    buttons.set(level.level_id,button);button.onclick=()=>choose(level.level_id);
    button.onkeydown=event=>{
      const index=graph.levels.findIndex(row=>row.level_id===level.level_id);
      const target=event.key==="ArrowDown"?graph.levels[index+1]:event.key==="ArrowUp"?graph.levels[index-1]:event.key==="Home"?graph.levels[0]:event.key==="End"?graph.levels.at(-1):null;
      if(target){event.preventDefault();buttons.get(target.level_id).focus();}
    };
    return item;
  }
  const roots=document.createElement("ul");roots.className="level-roots";roots.setAttribute("aria-label","公共入口");roots.append(...graph.roots.map(node));stage.append(roots);
  for(const lane of graph.lanes){
    const section=document.createElement("section"),title=document.createElement("h3"),list=document.createElement("ol");
    section.className="level-lane";section.dataset.chapterId=lane.id;title.textContent=lane.title;list.className="level-lane-list";
    list.append(...lane.levels.map(node));section.append(title,list);stage.append(section);
  }
  function edges(){
    if(!dialog.open)return;
    const origin=stage.getBoundingClientRect(),width=stage.clientWidth,height=stage.offsetHeight;svg.setAttribute("viewBox",`0 0 ${width} ${height}`);
    svg.setAttribute("width",width);svg.setAttribute("height",height);
    svg.replaceChildren(...graph.edges.map(edge=>{
      const a=buttons.get(edge.from).getBoundingClientRect(),b=buttons.get(edge.to).getBoundingClientRect();
      const x=a.left+a.width/2-origin.left,y=a.bottom-origin.top,tx=b.left+b.width/2-origin.left,ty=b.top-origin.top;
      const path=document.createElementNS("http://www.w3.org/2000/svg","path"),mid=y+Math.min(18,(ty-y)/2);
      const lane=graph.lanes.findIndex(lane=>lane.levels.some(level=>level.level_id===edge.to));
      const verticalGroup=Math.abs(x-tx)<1&&ty-y>200;
      path.setAttribute("d",verticalGroup?`M ${x} ${y} V ${y+18} H ${8+lane*4} V ${ty-18} H ${tx} V ${ty}`:`M ${x} ${y} V ${mid} H ${tx} V ${ty}`);path.dataset.from=edge.from;path.dataset.to=edge.to;
      path.setAttribute("class",(progress?.completed_levels??[]).includes(edge.from)?"edge-open":"edge-locked");return path;
    }));
  }
  function renderDetails(){
    const level=graph.byId.get(selected);if(!level||!progress)return;
    const state=levelState(level,progress,current);
    $("level-detail-title").textContent=level.title;$("level-detail-description").textContent=level.description??level.problem;
    $("level-detail-state").textContent=labels[state.status]+(state.current?" · 当前关卡":"")+(progress.developer_mode?" · 开发者可自由练习":"");
    $("level-prerequisites").replaceChildren(...level.prerequisites.map(id=>{
      const item=document.createElement("li");item.textContent=((progress.completed_levels??[]).includes(id)?"✓ 已通关：":"○ 尚未通关：")+graph.byId.get(id).title;return item;
    }));
    $("level-no-prerequisites").hidden=Boolean(level.prerequisites.length);
    $("level-lock-reason").textContent=state.missing.length?"缺少前置："+state.missing.map(id=>graph.byId.get(id).title).join("、")+(progress.developer_mode?"；开发者模式允许练习。":"。"):
      state.status==="locked"?"当前存档尚未授权此关，请刷新进度。":"前置已满足，可开始或重玩。";
    $("level-preview-hints").replaceChildren(...(level.hints??[]).map(text=>{const item=document.createElement("li");item.textContent=text;return item;}));
    $("start-selected-level").disabled=starting||state.status==="locked";
    $("start-selected-level").textContent=state.current?"开始 / 重试":state.status==="completed"?"重玩本关":"开始本关";
    $("start-selected-level").dataset.levelId=level.level_id;
  }
  function update(value){
    progress=value;
    const next=JSON.stringify([value.completed_levels,value.unlocked_levels,value.developer_mode]);
    if(next===signature)return;signature=next;
    $("level-tree-progress").textContent=`已通关 ${value.completed_levels.length} / ${graph.levels.length} · ${value.developer_mode?"开发者练习不计进度":"可任选已开放主线，实线表示必须通关的前置"}`;
    for(const level of graph.levels){
      const button=buttons.get(level.level_id),state=levelState(level,value,current);
      button.dataset.state=state.status;button.dataset.current=String(state.current);button.setAttribute("aria-pressed",String(level.level_id===selected));
      if(state.current)button.setAttribute("aria-current","page");else button.removeAttribute("aria-current");
      button.querySelector(".level-node-status").textContent=labels[state.status]+(state.current?" · 当前关卡":"");
      button.setAttribute("aria-label",level.title+"，"+labels[state.status]+(state.current?"，当前关卡":""));
    }
    renderDetails();requestAnimationFrame(edges);
  }
  function open(id,button){
    if(id&&graph.byId.has(id))choose(id);
    opener=button??document.activeElement;releaseControls();
    if(!dialog.open)dialog.showModal();$("open-level-tree").setAttribute("aria-expanded","true");
    renderDetails();requestAnimationFrame(edges);buttons.get(selected)?.focus({preventScroll:true});
  }
  $("open-level-tree").onclick=event=>open(null,event.currentTarget);
  $("choose-level").onclick=event=>open(null,event.currentTarget);
  $("close-level-tree").onclick=()=>dialog.close();
  dialog.addEventListener("close",()=>{$("open-level-tree").setAttribute("aria-expanded","false");(opener?.isConnected?opener:$("arena")).focus({preventScroll:true});});
  $("start-selected-level").onclick=async()=>{
    if($("start-selected-level").disabled)return;
    $("level-tree-error").textContent="";
    try{await onStart(selected);}catch(error){$("level-tree-error").textContent=error.message;}
  };
  const observer=new ResizeObserver(edges);observer.observe(stage);
  window.addEventListener("pagehide",()=>observer.disconnect(),{once:true});
  return {update,open,setStarting(value){starting=value;renderDetails();},announce(ids){
    const entries=ids.filter(id=>graph.byId.has(id));if(!entries.length)return;
    $("newly-unlocked").hidden=false;
    $("newly-unlocked-title").textContent="新解锁 · 请选择接下来的挑战";
    $("newly-unlocked-list").replaceChildren(...entries.map(id=>{
      const button=document.createElement("button");button.type="button";button.textContent=graph.byId.get(id).title;button.dataset.levelId=id;
      button.onclick=event=>open(id,event.currentTarget);return button;
    }));
  }};
}
