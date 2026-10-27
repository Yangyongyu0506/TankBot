// Small SDK hints from declared annotations and lesson parameters; no player code execution.
const escaped=text=>text.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
const fields=type=>[...(type?.fields??[]),...(type?.properties??[])];
export function referenceType(reference,expression,source){
  const direct=reference.types?.find(type=>type.name===expression);
  if(direct)return direct;
  const indexed=expression.match(/^([A-Za-z_]\w*)\[\d+\]$/);
  if(indexed){
    const declarations=[...source.matchAll(new RegExp("\\b"+escaped(indexed[1])+"\\s*:\\s*((?:tuple|typing\\.Tuple)\\s*\\[\\s*[A-Za-z_][\\w.]*\\s*,\\s*\\.\\.\\.\\s*\\])","g"))];
    const annotation=declarations.at(-1)?.[1]??reference.lesson?.aliases?.[indexed[1]]??"";
    const item=annotation.match(/^(?:tuple|typing\.Tuple)\s*\[\s*([A-Za-z_][\w.]*)\s*,\s*\.\.\.\s*\]$/)?.[1];
    return reference.types?.find(type=>type.name===item)??null;
  }
  const declarations=[...source.matchAll(new RegExp("\\b"+escaped(expression)+"\\s*:\\s*([A-Za-z_][A-Za-z0-9_.]*)","g"))];
  let name=declarations.at(-1)?.[1]??reference.lesson?.aliases?.[expression];
  if(name==="NDArray"||name==="np.ndarray")name="ndarray";
  return reference.types?.find(type=>type.name===name)??null;
}

export function symbolHelp(reference,expression,source){
  const dot=expression.lastIndexOf(".");
  if(dot>=0){
    const type=referenceType(reference,expression.slice(0,dot),source),field=expression.slice(dot+1);
    const item=fields(type).find(value=>value.name===field)??type?.methods.find(value=>value.name===field);
    if(item)return {title:`${expression}${item.type?": "+item.type:""}`,description:item.description,type:type.name};
  }
  const type=referenceType(reference,expression,source);
  return type?{title:expression===type.name?type.name:`${expression}: ${type.name}`,description:type.description,type:type.name,
    fields:fields(type).map(field=>`${field.name}: ${field.type} — ${field.description}`)}:null;
}

export function sdkCompletions(reference,source,position,explicit=false){
  const before=source.slice(0,position),member=before.match(/([A-Za-z_]\w*(?:\[\d+\])?(?:\.[A-Za-z_]\w*)*)\.([A-Za-z_0-9]*)$/);
  if(member){
    const type=referenceType(reference,member[1],source);
    if(!type)return null;
    return {from:position-member[2].length,options:[...fields(type).map(field=>({label:field.name,type:"property",detail:field.type,info:field.description,boost:99})),
      ...type.methods.map(method=>({label:method.name,type:"method",detail:method.signature,info:method.description,boost:99}))]};
  }
  const word=before.match(/[A-Za-z_][A-Za-z0-9_]*$/);
  if(!explicit&&(!word||word[0].length<2))return null;
  return {from:position-(word?.[0].length??0),options:(reference.types??[]).map(type=>({label:type.name,type:"class",info:type.description}))};
}
