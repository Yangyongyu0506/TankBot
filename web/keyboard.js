// These virtual control IDs adapt to the existing controller, not to physical defaults.
// Physical bindings come exclusively from the YAML settings via setBindings().
export const controlKeys={forward:"KeyW",backward:"KeyS",left:"KeyA",right:"KeyD",turn_left:"KeyQ",turn_right:"KeyE",turret_left:"KeyJ",turret_right:"KeyL",fire:"Space"};
export const labels={forward:"前进",backward:"后退",left:"左转 / 全向左移",right:"右转 / 全向右移",turn_left:"全向车体左转",turn_right:"全向车体右转",turret_left:"炮台左转",turret_right:"炮台右转",fire:"单发",editor:"打开 / 收起代码编辑器",help:"关卡说明 / 类型",settings:"打开 / 收起设置"};
let bindings={};
export function setBindings(value){bindings={...value};}
export function binding(action){return bindings[action];}
export function shortcut(event,action){return event.code===binding(action)&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.shiftKey&&!event.isComposing;}
export function controlKey(code){const action=Object.keys(bindings).find(name=>bindings[name]===code);return controlKeys[action]??null;}
export function keyLabel(code){return ({Space:"空格",ArrowUp:"↑",ArrowDown:"↓",ArrowLeft:"←",ArrowRight:"→"})[code]??code.replace(/^Key|^Digit/,"");}
export function validCode(code){return /^(Key[A-Z]|Digit[0-9]|Arrow(Up|Down|Left|Right)|Space|F([1-9]|1[0-2])|Numpad[0-9])$/.test(code);}
export function bindingHint(text){
  const actions={...Object.fromEntries(Object.entries(controlKeys).map(([action,code])=>[keyLabel(code),action])),F1:"help",F2:"editor"};
  return text.replace(/\b(F1|F2|[WSADQEJL])\b|空格/g,key=>keyLabel(binding(actions[key])));
}
