// File paths are data: build a shared directory tree and render names as text only.
export function fileTreeRows(paths,editFiles=[]){
  const root=new Map(),highlight=new Set(editFiles),rows=[];
  for(const path of [...paths].sort()){
    let children=root;
    const parts=path.split('/');
    parts.forEach((name,index)=>{
      const directory=index<parts.length-1;
      if(!children.has(name))children.set(name,{name,path:parts.slice(0,index+1).join('/'),directory,children:new Map()});
      children=children.get(name).children;
    });
  }
  function visit(children,prefix='',depth=1){
    const nodes=[...children.values()].sort((a,b)=>Number(b.directory)-Number(a.directory)||(a.name<b.name?-1:a.name>b.name?1:0));
    nodes.forEach((node,index)=>{
      const last=index===nodes.length-1;
      rows.push({path:node.path,name:node.name,directory:node.directory,prefix:prefix+(last?'└── ':'├── '),depth,highlight:!node.directory&&highlight.has(node.path)});
      if(node.directory)visit(node.children,prefix+(last?'    ':'│   '),depth+1);
    });
  }
  visit(root);return rows;
}

export function renderFileTree(container,files,{selected,dirtyPaths=[],editFiles=[],onOpen}){
  const dirty=new Set(dirtyPaths),fragment=document.createDocumentFragment();
  const legend=document.createElement('div');legend.className='file-tree-help';legend.textContent='高亮：本关编辑文件';fragment.append(legend);
  const root=document.createElement('div');root.className='file-tree-root';root.textContent='workspace/';fragment.append(root);
  for(const row of fileTreeRows(Object.keys(files),editFiles)){
    const line=document.createElement('div');line.className='file-tree-row';
    const prefix=document.createElement('span');prefix.className='file-tree-guides';prefix.textContent=row.prefix;prefix.setAttribute('aria-hidden','true');
    const name=document.createElement(row.directory?'span':'button');name.textContent=row.name+(row.directory?'/':dirty.has(row.path)?' *':'');
    if(row.directory){name.className='file-tree-directory';}
    else{
      name.type='button';name.title=row.path;name.dataset.path=row.path;name.dataset.taskFile=String(row.highlight);
      name.classList.toggle('selected',row.path===selected);name.classList.toggle('task-file',row.highlight);
      name.setAttribute('aria-label',row.path+(row.highlight?'，本关编辑文件':''));
      if(row.path===selected)name.setAttribute('aria-current','true');
      name.onclick=()=>onOpen(row.path);
    }
    line.append(prefix,name);fragment.append(line);
  }
  const top=container.scrollTop,left=container.scrollLeft;
  container.replaceChildren(fragment);container.scrollTop=top;container.scrollLeft=left;
}

export function revealSelectedFile(container){
  const row=container.querySelector('button.selected')?.parentElement;
  if(!row||!container.clientHeight)return;
  const file=row.getBoundingClientRect(),pane=container.getBoundingClientRect();
  if(file.bottom>pane.bottom)container.scrollTop+=file.bottom-pane.bottom;
  else if(file.top<pane.top)container.scrollTop-=pane.top-file.top;
}
