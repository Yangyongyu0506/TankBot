import {EditorView, basicSetup} from "codemirror";
import {EditorState, Compartment} from "@codemirror/state";
import {keymap} from "@codemirror/view";
import {indentWithTab} from "@codemirror/commands";
import {python} from "@codemirror/lang-python";
import {json} from "@codemirror/lang-json";
import {vim, Vim} from "@replit/codemirror-vim";

export function createEditor(parent, changed, save){
  const language=new Compartment(), mode=new Compartment();
  let current="",states=new Map(),vimEnabled=false;
  const theme=EditorView.theme({
    "&":{height:"100%",minHeight:"0",backgroundColor:"#10191d",color:"#d8e9df",fontSize:"13px"},
    ".cm-scroller":{overflow:"auto",fontFamily:"ui-monospace, SFMono-Regular, Consolas, monospace"},
    ".cm-content":{caretColor:"#8fe3b5"},".cm-gutters":{backgroundColor:"#10191d",color:"#6f8c80",border:"none"},
    ".cm-activeLine, .cm-activeLineGutter":{backgroundColor:"#183029"},
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground":{backgroundColor:"#355548"},
  },{dark:true});
  const extensions=()=>[mode.of(vimEnabled?vim():[]),basicSetup,language.of(current.endsWith(".json")?json():python()),
    keymap.of([{key:"Mod-s",run:()=>{save();return true;}},indentWithTab]),theme,
    EditorView.updateListener.of(update=>{if(update.docChanged)changed(current,update.state.doc.toString());})];
  const view=new EditorView({parent,state:EditorState.create({extensions:extensions()})});
  Vim.defineEx("write","w",()=>save());
  return {
    open(path,source){
      if(current)states.set(current,view.state);
      current=path;
      let state=states.get(path);
      if(!state||state.doc.toString()!==source)state=EditorState.create({doc:source,extensions:extensions()});
      view.setState(state);
      view.dispatch({effects:[mode.reconfigure(vimEnabled?vim():[]),language.reconfigure(path.endsWith(".json")?json():python())]});
    },
    vim(enabled){vimEnabled=enabled;view.dispatch({effects:mode.reconfigure(enabled?vim():[])});view.focus();},
    go(line){const position=view.state.doc.line(Math.max(1,Math.min(line,view.state.doc.lines))).from;view.dispatch({selection:{anchor:position},scrollIntoView:true});view.focus();},
    focus(){view.focus();},
    destroy(){view.destroy();}
  };
}
