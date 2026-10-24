import {EditorView, basicSetup} from "codemirror";
import {EditorState, Compartment} from "@codemirror/state";
import {keymap, hoverTooltip} from "@codemirror/view";
import {indentWithTab} from "@codemirror/commands";
import {HighlightStyle, syntaxHighlighting} from "@codemirror/language";
import {tags} from "@lezer/highlight";
import {python, pythonLanguage} from "@codemirror/lang-python";
import {json} from "@codemirror/lang-json";
import {vim, Vim} from "@replit/codemirror-vim";
import {sdkCompletions, symbolHelp} from "./sdk-hints.js";

export function createEditor(parent, changed, save, reference={}){
  const language=new Compartment(), mode=new Compartment();
  let current="",states=new Map(),vimEnabled=false;
  const theme=EditorView.theme({
    "&":{height:"100%",minHeight:"0",backgroundColor:"#10191d",color:"#d8e9df",fontSize:"13px"},
    ".cm-scroller":{overflow:"auto",fontFamily:"ui-monospace, SFMono-Regular, Consolas, monospace"},
    ".cm-content":{caretColor:"#8fe3b5"},".cm-gutters":{backgroundColor:"#10191d",color:"#6f8c80",border:"none"},
    ".cm-activeLine, .cm-activeLineGutter":{backgroundColor:"#183029"},
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground":{backgroundColor:"#355548"},
  },{dark:true});
  const highlighting=HighlightStyle.define([
    {tag:tags.keyword,color:"#c8a3e8"},
    {tag:[tags.string,tags.special(tags.string)],color:"#b8d99b"},
    {tag:tags.comment,color:"#91a99e"},
    {tag:[tags.number,tags.bool,tags.null],color:"#e9b58b"},
    {tag:[tags.typeName,tags.className],color:"#e6d78a"},
    {tag:tags.function(tags.variableName),color:"#8fe3b5"},
    {tag:[tags.operator,tags.punctuation],color:"#b0ccda"},
  ]);
  const extensions=()=>[mode.of(vimEnabled?vim():[]),basicSetup,language.of(current.endsWith(".json")?json():python()),
    syntaxHighlighting(highlighting),
    pythonLanguage.data.of({autocomplete:context=>sdkCompletions(reference,context.state.doc.toString(),context.pos,context.explicit)}),
    hoverTooltip((editor,pos)=>{
      if(!current.endsWith(".py"))return null;
      const line=editor.state.doc.lineAt(pos),offset=pos-line.from;
      const left=line.text.slice(0,offset).match(/[A-Za-z_][\w.]*$/)?.[0]??"",right=line.text.slice(offset).match(/^[\w]*/)?.[0]??"";
      const help=symbolHelp(reference,left+right,editor.state.doc.toString());if(!help)return null;
      return {pos:pos-left.length,end:pos+right.length,above:true,create(){
        const dom=document.createElement("div");dom.className="sdk-tooltip";
        const title=document.createElement("strong"),text=document.createElement("p");title.textContent=help.title;text.textContent=help.description;dom.append(title,text);
        for(const field of help.fields??[]){const row=document.createElement("div");row.textContent=field;dom.append(row);}return {dom};
      }};
    }),
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
