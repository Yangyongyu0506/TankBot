// Store maintenance is explicitly previewed. The game runtime never imports backups itself.
export function storageSummary(inventory){
  const names={current:'当前版本',history:'历史版本',archives:'测试/部署归档',backups:'压缩备份',recovery:'可恢复区',experiments:'实验记录',metadata:'元数据'};
  return Object.entries(inventory.categories).map(([key,value])=>({key,name:names[key]??key,...value}));
}
export function mountStorage({request,beforeOpen,onRestored}){
  const $=id=>document.getElementById(id),dialog=$('storage-dialog');let inventory,plan,busy=false;
  const message=text=>{$('storage-message').textContent=text;};
  async function refresh(){inventory=await request('storage',{});render();}
  async function action(fn){
    if(busy)return;busy=true;dialog.dataset.busy='true';
    const controls=[...dialog.querySelectorAll('button:not(#close-storage),input,select')].map(element=>[element,element.disabled]);
    controls.forEach(([element])=>{element.disabled=true;});
    try{await fn();}catch(error){message(error.message);}
    finally{busy=false;dialog.dataset.busy='false';controls.forEach(([element,disabled])=>{if(element.isConnected)element.disabled=disabled;});}
  }
  function render(){
    $('storage-total').textContent=`当前课程项目共 ${(inventory.total_bytes/1024).toFixed(1)} KiB${inventory.total_bytes>=inventory.warning_bytes?' · 已达到提示阈值，请检查备份和历史容量':''}`;
    $('storage-summary').replaceChildren(...storageSummary(inventory).map(row=>{const p=document.createElement('p');p.textContent=`${row.name}：${row.count}项 / ${(row.bytes/1024).toFixed(1)} KiB`;return p;}));
    if(!$('storage-keep').value)$('storage-keep').value=inventory.limits.keep_recent_revisions;
    const versions=$('storage-versions');versions.replaceChildren(...inventory.revisions.map(row=>{
      const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=row.pinned;input.disabled=row.current;input.dataset.revision=row.revision;
      input.onchange=()=>action(async()=>{await request('pin',{revision:inventory.revision,target_revision:row.revision,enabled:input.checked});await refresh();});
      label.append(input,document.createTextNode(`${row.current?'当前 · ':''}${row.revision.slice(0,12)} · ${(row.bytes/1024).toFixed(1)} KiB`));return label;
    }));
    $('storage-archives').replaceChildren(...inventory.archives.map(row=>{const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.archive=row.id;label.append(input,document.createTextNode(`${row.id.slice(0,12)} · revision ${row.revision.slice(0,12)}`));return label;}));
    $('storage-recovery').replaceChildren(...inventory.recovery.map(item=>{const row=document.createElement('div'),restore=document.createElement('button'),purge=document.createElement('button');
      row.textContent=`${item.id.slice(0,12)} · ${item.state} · ${Object.keys(item.files).length}项 `;
      restore.textContent='恢复历史';restore.onclick=()=>action(async()=>{await request('recovery_restore',{id:item.id,revision:inventory.revision});await refresh();message('历史已恢复，当前代码保持原版本。');});
      purge.textContent='清空回收副本（压缩备份仍保留）';purge.disabled=['purged','rolled_back'].includes(item.state);
      purge.onclick=()=>{plan={kind:'purge',id:item.id,base_revision:inventory.revision};showPlan({message:'这会永久移除回收区副本；服务器先验证压缩备份可恢复。压缩备份仍占空间，当前版本与固定版本不受影响。',...plan});};
      row.append(restore,purge);return row;
    }));
    $('storage-backups').replaceChildren(...inventory.backups.map(name=>{const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.backup=name.slice(7,-8);label.append(input,document.createTextNode(name));return label;}));
    dialog.dataset.totalBytes=inventory.total_bytes;
  }
  function showPlan(value){plan=value;$('storage-preview').textContent=JSON.stringify(value,null,2);$('storage-apply').hidden=false;$('storage-apply').textContent=value.kind==='restore'?'确认恢复并切换当前代码':value.kind==='purge'?'确认清空回收副本':value.kind==='backup_cleanup'?'确认永久删除冗余备份':'确认备份并移入恢复区';}
  $('open-storage').onclick=()=>action(async()=>{await beforeOpen();dialog.showModal();await refresh();message('只管理当前课程项目；进度和设置文件请另行备份userdata。');});
  $('close-storage').onclick=()=>dialog.close();
  $('storage-export').onclick=()=>action(async()=>{
    const value=await request('backup_export',{}),url=URL.createObjectURL(new Blob([JSON.stringify(value)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download=`tankbot-project-backup-${value.sha256.slice(0,12)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);await refresh();message('已生成服务器压缩备份并导出完整项目（当前、历史、归档、固定版本与实验记录）。');
  });
  $('storage-import').onchange=event=>action(async()=>{const file=event.target.files[0];if(!file)return;if(file.size>inventory.limits.max_backup_bytes)throw Error('备份超过总量限制');showPlan(await request('backup_preview',{revision:inventory.revision,backup:JSON.parse(await file.text())}));event.target.value='';});
  $('storage-plan').onclick=()=>action(async()=>{const archives=[...$('storage-archives').querySelectorAll('input:checked')].map(input=>input.dataset.archive);showPlan(await request('cleanup_plan',{revision:inventory.revision,keep_recent:Number($('storage-keep').value),archives}));});
  $('storage-plan-backups').onclick=()=>action(async()=>{const backup_ids=[...$('storage-backups').querySelectorAll('input:checked')].map(input=>input.dataset.backup);showPlan(await request('backup_cleanup_plan',{revision:inventory.revision,backup_ids}));});
  $('storage-apply').onclick=()=>action(async()=>{
    if(!plan)return;
    const value=plan;
    if(value.kind==='restore'){await request('backup_apply',{revision:value.base_revision,plan_id:value.plan_id});message('已恢复并原子切换HEAD；当前旧版本的完整备份保留。请重新测试部署。');onRestored();}
    else if(value.kind==='purge')await request('recovery_purge',{revision:value.base_revision,id:value.id});
    else if(value.kind==='backup_cleanup')await request('backup_cleanup_apply',{revision:value.base_revision,plan_id:value.plan_id});
    else await request('cleanup_apply',{revision:value.base_revision,plan_id:value.plan_id});
    plan=null;$('storage-apply').hidden=true;$('storage-preview').textContent='';await refresh();
  });
  $('storage-cancel').onclick=()=>{plan=null;$('storage-apply').hidden=true;$('storage-preview').textContent='已取消预览，没有清理文件。';};
}
