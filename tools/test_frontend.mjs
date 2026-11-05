#!/usr/bin/env node
// Local and CI share discovery. The native/WASM equivalence probe needs built artifacts.
import {readdir} from "node:fs/promises";
import {resolve,join} from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";

const root=fileURLToPath(new URL("../",import.meta.url));
const args=process.argv.slice(2),wasm=args.includes("--wasm"),list=args.includes("--list");
let directory=join(root,"tests");
for(let i=0;i<args.length;i++){
  if(args[i]==="--directory"&&args[i+1])directory=resolve(args[++i]);
  else if(!["--wasm","--list"].includes(args[i])){console.error(`Unknown argument: ${args[i]}`);process.exit(2);}
}
async function discover(path){
  const files=[];
  for(const entry of await readdir(path,{withFileTypes:true})){
    if(entry.isDirectory())files.push(...await discover(join(path,entry.name)));
    else if(entry.isFile()&&/^test_.*\.mjs$/.test(entry.name)&&((entry.name==="test_wasm.mjs")===wasm))files.push(join(path,entry.name));
  }
  return files.sort();
}
try{
  const files=await discover(directory);
  if(!files.length)throw Error("No tests discovered; refusing an empty successful run");
  if(list)console.log(JSON.stringify(files));
  else{
    for(const file of files){
      console.log(`TEST: ${file}`);
      const result=spawnSync(process.execPath,[file],{cwd:root,stdio:"inherit"});
      if(result.error)throw result.error;
      if(result.status!==0)process.exitCode=result.status??1;
    }
  }
}catch(error){console.error(error.message);process.exitCode=2;}
