// Read-only learning aids share no world state, runtime handles or player source execution.
const element=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};

export function mountLearning(reference,openFile,previewTemplate){
  const $=id=>document.getElementById(id),pane=$("learning-pane"),grid=pane.parentElement;
  let currentType=reference.lesson.default_type;
  function show(open=true){pane.hidden=!open;grid.classList.toggle("with-learning",open);$("toggle-learning").setAttribute("aria-expanded",String(open));}
  function tab(name){
    for(const button of pane.querySelectorAll("[role=tab]")){
      const selected=button.dataset.tab===name;button.setAttribute("aria-selected",String(selected));
      $(button.getAttribute("aria-controls")).hidden=!selected;
    }
  }
  for(const button of pane.querySelectorAll("[role=tab]"))button.onclick=()=>tab(button.dataset.tab);
  $("toggle-learning").onclick=()=>show(pane.hidden);
  $("close-learning").onclick=()=>show(false);
  window.addEventListener("keydown",event=>{
    if(event.code!=="F1")return;
    event.preventDefault();event.stopImmediatePropagation();
    const wasOpen=$("workspace-dialog").open;
    if(!wasOpen)$("open-workspace").click();
    show(!wasOpen||pane.hidden);if(!pane.hidden)$("learning-title").focus();
  },{capture:true});
  const lesson=$("learning-lesson");lesson.append(element("h3",reference.lesson.title),element("p",reference.lesson.summary));
  lesson.append(element("h4","完成条件"),element("p",reference.lesson.completion),element("h4","调用与状态"),element("p",reference.lesson.execution));
  const steps=element("ol");for(const text of reference.lesson.steps)steps.append(element("li",text));lesson.append(steps);
  for(const file of reference.lesson.files){const button=element("button","打开 "+file.path);button.onclick=()=>{openFile(file.path);if(innerWidth<1050)show(false);};lesson.append(button,element("p",file.role,"hint"));}
  for(const fn of reference.lesson.functions){
    const section=element("section",undefined,"function-guide");section.append(element("h4","填写约定"),element("pre",fn.signature));
    for(const parameter of fn.parameters){const button=element("button",`${parameter.name}: ${parameter.type}`);button.onclick=()=>selectType(parameter.type.split(/[\[ |]/)[0]);section.append(button);}
    section.append(element("p","返回类型："+fn.returns),element("pre",fn.description));lesson.append(section);
  }
  lesson.append(element("h4","文件已准备好"),element("p","只编辑算法文件中的 TODO。导入、检测列表展开、矩阵乘法、消息发布、测试和部署由系统脚手架承担；框架文件与 JSON 配置可保持原样。"));
  lesson.append(element("h4","常见问题"));
  for(const text of reference.lesson.common_errors)lesson.append(element("p",text));
  lesson.append(element("h4","测试快照会检查什么？"));
  for(const text of reference.testing.checks)lesson.append(element("p",text));
  lesson.append(element("p",reference.testing.meaning));
  let upgradeNotice;
  function updateUpgrade(required){
    upgradeNotice?.remove();upgradeNotice=null;
    if(!required)return;
    upgradeNotice=element("section",undefined,"learning-upgrade");upgradeNotice.append(element("strong","需要更新课程运行框架"),element("p","这是项目兼容性检查，尚未测试你的算法。预览后可保留 perception/ 等算法文件，更新运行框架并继续测试。"));
    const button=element("button","预览更新（保留算法）");button.onclick=()=>{show(false);previewTemplate();};upgradeNotice.append(button);lesson.prepend(upgradeNotice);
  }
  updateUpgrade(reference.upgrade_required);
  function selectType(name){
    if(!reference.types.some(type=>type.name===name))return;
    currentType=name;tab("types");show(true);renderType();
  }
  function renderType(){
    const type=reference.types.find(value=>value.name===currentType);if(!type)return;
    const detail=$("type-detail");detail.replaceChildren(element("h3",type.name),element("p",type.description));
    detail.append(element("h4","构造方式"),element("pre",type.constructor));
    detail.append(element("pre",`class ${type.name}:\n`+(type.fields.length?type.fields.map(field=>`    ${field.name}: ${field.type}`).join("\n"):"    # 公开方法如下")));
    const table=element("dl");
    for(const field of type.fields)table.append(element("dt",`${field.name}: ${field.type}`),element("dd",field.description));
    for(const method of type.methods)table.append(element("dt",method.signature),element("dd",method.description));
    detail.append(table);
  }
  function search(){
    const query=$("type-search").value.toLowerCase();
    $("type-list").replaceChildren(...reference.types.filter(type=>(type.name+" "+type.description+" "+type.fields.map(field=>field.name).join(" ")).toLowerCase().includes(query)).map(type=>{
      const button=element("button",type.name);button.onclick=()=>selectType(type.name);return button;
    }));
  }
  $("type-search").oninput=search;search();renderType();
  for(const topic of reference.python)$("learning-python").append(element("h3",topic.title),element("p",topic.text),element("pre",topic.code));
  setupMatrixLab($("learning-matrix"));
  show(reference.lesson.functions.length>0||reference.lesson.title.startsWith("C0"));
  return {
    open:()=>{show(true);tab("lesson");},
    selectType,
    updateUpgrade,
    file(path){
      const fn=reference.lesson.functions.find(item=>item.path===path);
      $("editor-contract").textContent=fn?.signature??"F1 · 关卡说明、类型与 Python 速查";
      $("editor-contract").title=fn?.description??"";
    }
  };
}

function setupMatrixLab(container){
  container.append(element("h3","矩阵乘法把基向量加权相加"),element("p","T 的前三列是雷达基向量在地图中的方向，第四列是雷达原点。改变下面的数值，查看每一行的点积。这里使用独立教学数据，不读取当前世界。"));
  const controls=element("div",undefined,"matrix-controls"),inputs={};
  for(const [key,label,value] of [["x","原点 x / m",1],["y","原点 y / m",3],["yaw","yaw / °",90],["px","点 x / m",2],["py","点 y / m",0]]){
    const wrapper=element("label",label),input=element("input");input.type="number";input.step=key==="yaw"?15:.5;input.value=value;input.setAttribute("aria-label",label);input.id="matrix-"+key;inputs[key]=input;wrapper.append(input);controls.append(wrapper);
  }
  const kind=element("select");kind.id="matrix-kind";kind.setAttribute("aria-label","齐次坐标类型");
  for(const [value,text] of [[1,"点：w=1，包含平移"],[0,"方向：w=0，不包含平移"]]){const option=element("option",text);option.value=value;kind.append(option);}controls.append(kind);container.append(controls);
  const canvas=element("canvas");canvas.width=480;canvas.height=250;canvas.id="matrix-canvas";canvas.setAttribute("aria-label","两个坐标系及变换后的点示意");
  const calculation=element("div");calculation.id="matrix-calculation";calculation.setAttribute("aria-live","polite");container.append(canvas,calculation);
  function update(){
    const values=Object.fromEntries(Object.entries(inputs).map(([key,input])=>[key,Number(input.value)]));
    if(Object.values(values).some(value=>!Number.isFinite(value)||Math.abs(value)>1e6))return;
    const angle=values.yaw*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle),w=Number(kind.value);
    const matrix=[[c,-s,0,values.x],[s,c,0,values.y],[0,0,1,0],[0,0,0,1]],point=[values.px,values.py,0,w];
    const result=matrix.map(row=>row.reduce((sum,value,index)=>sum+value*point[index],0));
    const format=value=>Math.abs(value)<1e-9?"0":Number(value.toFixed(3)).toString();
    calculation.replaceChildren(element("pre","T_map_radar =\n"+matrix.map(row=>"[ "+row.map(format).join(", ")+" ]").join("\n")),element("pre","p_radar = ["+point.map(format).join(", ")+"]"));
    for(const [i,row] of matrix.entries())calculation.append(element("p",`${["x_map","y_map","z_map","w"][i]} = `+row.map((value,index)=>`${format(value)} × ${format(point[index])}`).join(" + ")+` = ${format(result[i])}`));
    calculation.append(element("strong","T @ p = ["+result.map(format).join(", ")+"]"));
    const ctx=canvas.getContext("2d"),scale=Math.min(canvas.width,canvas.height)/(2*Math.max(4,...result.slice(0,2).map(Math.abs),Math.abs(values.x),Math.abs(values.y))+2);
    const project=(x,y)=>[canvas.width/2+x*scale,canvas.height/2-y*scale];
    ctx.clearRect(0,0,canvas.width,canvas.height);
    function arrow(origin,delta,color,label){
      const a=project(...origin),b=project(origin[0]+delta[0],origin[1]+delta[1]);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.beginPath();ctx.arc(...b,3,0,Math.PI*2);ctx.fill();ctx.fillText(label,b[0]+4,b[1]-4);
    }
    ctx.font="12px sans-serif";arrow([0,0],[1,0],"#d99ba6","map +x");arrow([0,0],[0,1],"#82b9f0","map +y");arrow([values.x,values.y],[c,s],"#8fe3b5","radar +x");arrow([values.x,values.y],[-s,c],"#e6d78a","radar +y");
    arrow(w?[values.x,values.y]:[0,0],w?[result[0]-values.x,result[1]-values.y]:result.slice(0,2),"#f4ac6e",w?"变换后的点":"变换后的方向");
    canvas.dataset.result=JSON.stringify(result);canvas.dataset.matrix=JSON.stringify(matrix);
  }
  for(const input of Object.values(inputs))input.oninput=update;kind.onchange=update;update();
}
