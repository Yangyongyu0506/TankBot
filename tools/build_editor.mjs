import {build} from 'esbuild';
import {readFile,writeFile,readdir} from 'node:fs/promises';
await build({entryPoints:['web/editor.js'],bundle:true,format:'esm',target:'es2022',outfile:'build/web/editor-bundle.js',legalComments:'linked'});
const lock=JSON.parse(await readFile('package-lock.json','utf8'));
const notices=[];
for(const path of Object.keys(lock.packages).filter(p=>p&&!p.includes('/@esbuild/')&&!p.endsWith('/esbuild'))){
  const pkg=JSON.parse(await readFile(path+'/package.json','utf8'));
  const files=await readdir(path);
  const name=files.find(n=>/^licen[sc]e(?:\.\w+)?$/i.test(n));
  if(!name)throw Error('Missing license: '+path);
  notices.push(`${pkg.name} ${pkg.version}\n${pkg.repository?.url??''}\n${await readFile(path+'/'+name,'utf8')}`);
}
await writeFile('build/web/THIRD_PARTY_NOTICES.txt',notices.join('\n\n---\n\n'));
console.log('Editor bundle and third-party notices built.');
