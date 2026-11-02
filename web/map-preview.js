// Read-only, authority-filtered map explorer; it never changes the live scene.
export function mapBounds(walls){
  if(!walls.length)return null;
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(const {center:[x,y],size:[w,h]} of walls){
    minX=Math.min(minX,x-w/2);maxX=Math.max(maxX,x+w/2);
    minY=Math.min(minY,y-h/2);maxY=Math.max(maxY,y+h/2);
  }
  const width=maxX-minX,height=maxY-minY;
  if(![minX,minY,maxX,maxY,width,height].every(Number.isFinite)||width<=0||height<=0)return null;
  return {minX,minY,maxX,maxY,width,height};
}
export function mapProjection(bounds,width,height,padding=40){
  const scale=Math.min((width-2*padding)/bounds.width,(height-2*padding)/bounds.height);
  const cx=(bounds.minX+bounds.maxX)/2,cy=(bounds.minY+bounds.maxY)/2;
  return {scale,point:(x,y)=>[width/2+(x-cx)*scale,height/2-(y-cy)*scale]};
}
export function drawMapPreview(canvas,entry){
  const ctx=canvas.getContext('2d'),width=canvas.width,height=canvas.height;
  ctx.clearRect(0,0,width,height);ctx.fillStyle='#10241f';ctx.fillRect(0,0,width,height);
  const bounds=entry&&mapBounds(entry.walls);
  if(!bounds){ctx.fillStyle='#c1d8ce';ctx.font='20px sans-serif';ctx.fillText(entry?'无静态墙体':'本关未授权地图预览',40,60);return;}
  const {scale,point}=mapProjection(bounds,width,height);
  const step=10**Math.floor(Math.log10(Math.max(bounds.width,bounds.height)/10));
  ctx.strokeStyle='#244137';ctx.lineWidth=1;ctx.beginPath();
  for(let i=0;i<=Math.ceil(bounds.width/step);i++){const x=(Math.ceil(bounds.minX/step)+i)*step;if(x>bounds.maxX)break;const [px]=point(x,0);ctx.moveTo(px,40);ctx.lineTo(px,height-40);}
  for(let i=0;i<=Math.ceil(bounds.height/step);i++){const y=(Math.ceil(bounds.minY/step)+i)*step;if(y>bounds.maxY)break;const [,py]=point(0,y);ctx.moveTo(40,py);ctx.lineTo(width-40,py);}
  ctx.stroke();ctx.fillStyle='#80aa98';ctx.strokeStyle='#bed8cc';
  for(const {center:[x,y],size:[w,h]} of entry.walls){const [px,py]=point(x-w/2,y+h/2);ctx.fillRect(px,py,w*scale,h*scale);ctx.strokeRect(px,py,w*scale,h*scale);}
  const [ox,oy]=point(0,0);
  if(ox>=40&&ox<=width-40&&oy>=40&&oy<=height-40){
    ctx.strokeStyle='#e4bb76';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(ox,oy);ctx.lineTo(ox+30,oy);ctx.moveTo(ox,oy);ctx.lineTo(ox,oy-30);ctx.stroke();
    ctx.fillStyle='#e4bb76';ctx.font='14px monospace';ctx.fillText('+x',ox+33,oy+5);ctx.fillText('+y',ox-8,oy-36);ctx.fillText('0',ox-14,oy+18);
  }
  ctx.fillStyle='#c1d8ce';ctx.font='16px sans-serif';ctx.fillText(`网格 ${step.toPrecision(2)*1} m · +x → / +y ↑`,40,height-14);
}
export function mountMapPreview(releaseControls){
  const $=id=>document.getElementById(id),dialog=$('map-dialog'),button=$('open-map');
  let entries=[],generation=0;
  function render(){
    const entry=entries.find(item=>item.id===$('map-select').value);
    drawMapPreview($('map-preview'),entry);
    const bounds=entry&&mapBounds(entry.walls);
    $('map-size').textContent=bounds?`外包尺寸 ${bounds.width.toFixed(2)} × ${bounds.height.toFixed(2)} m · ${entry.walls.length} 面墙`:'';
    $('map-launch-command').textContent=entry&&entry.id!=='current'?`启动覆盖：python3 tools/tankbot.py serve --level c0 --map '${entry.id.replaceAll("'","'\\''")}'`:'';
    $('map-preview').dataset.mapId=entry?.id??'';
    $('map-preview').dataset.wallCount=String(entry?.walls.length??0);
  }
  async function refresh(){
    const serial=++generation;
    try{
      const response=await fetch('/api/maps'),data=await response.json();
      if(!response.ok)throw Error(data.error??'读取地图失败');
      if(serial!==generation)return;
      entries=[...(data.current?[data.current]:[]),...data.maps];
      const selected=$('map-select').value;
      $('map-select').replaceChildren(...entries.map(entry=>{const o=document.createElement('option');o.value=entry.id;o.textContent=entry.name;return o;}));
      if(entries.some(entry=>entry.id===selected))$('map-select').value=selected;
      $('map-select').disabled=!entries.length;
      $('map-practice-note').hidden=!data.overridden;
      $('map-preview-status').textContent=data.overridden?'当前使用启动参数指定的地图，重试/切关继续沿用；练习不计正式通关。':data.current?(data.developer?'开发者模式：可预览全部地图资产；当前场景位于列表首项。':'玩家模式：仅预览本关授权公开的当前地图。'):'本关未公开地图，预览不会绕过显示权限。';
      render();
    }catch(error){
      if(serial!==generation)return;
      entries=[];$('map-select').replaceChildren();render();$('map-preview-status').textContent=error.message;
    }
  }
  button.onclick=()=>{releaseControls();dialog.showModal();button.setAttribute('aria-expanded','true');$('close-map').focus();refresh();};
  $('close-map').onclick=()=>dialog.close();
  $('map-select').onchange=render;
  dialog.addEventListener('close',()=>{button.setAttribute('aria-expanded','false');$('arena').focus({preventScroll:true});});
  window.addEventListener('keydown',event=>{if(dialog.open){event.stopImmediatePropagation();}},{capture:true});
  // Populate the permanent practice badge without waiting for the first preview.
  refresh();
}
