"""Explicit backup, pinning and recoverable cleanup under the store's existing file lock/CAS."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from .workspace import digest,validate_files
from .engineering import settings
from tankbot_protocol.wire import strict_loads

HASH=r'[a-f0-9]{64}'
RECOVERY=r'recovery/[a-f0-9]{32}/(?:manifest|'+HASH+r'|archive-'+HASH+r')\.json'
ENTRY=re.compile(r'(?:'+HASH+r'\.json|archive-'+HASH+r'\.json|PINS\.json|experiments/'+HASH+r'\.json|'+RECOVERY+r')')


class WorkspaceMaintenance:
    def __init__(self,store):
        self.store=store;self.root=store.directory;self.limits=settings()['storage'];self.plans={}

    def _atomic(self,path,raw):
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)

    def _json(self,path,value):self._atomic(path,json.dumps(value,ensure_ascii=True,indent=2,allow_nan=False).encode())

    def _files(self):
        if self.root.is_symlink():raise ValueError('UNSAFE_WORKSPACE_STORAGE: root link')
        files=[]
        for path in self.root.rglob('*'):
            if path.is_symlink():raise ValueError('UNSAFE_WORKSPACE_STORAGE: symbolic link')
            if path.is_file():
                if path.stat().st_nlink!=1:raise ValueError('UNSAFE_WORKSPACE_STORAGE: hard link')
                files.append(path)
        return files

    def _pins(self):
        path=self.root/'PINS.json'
        if not path.exists():return []
        value=strict_loads(path.read_bytes())
        if (not isinstance(value,dict) or set(value)!={'version','revisions'} or value['version']!=1
                or not isinstance(value['revisions'],list) or len(value['revisions'])>self.limits['max_pins']
                or len(value['revisions'])!=len(set(value['revisions']))
                or any(not isinstance(v,str) or not re.fullmatch(HASH,v) for v in value['revisions'])):
            raise ValueError('INVALID_WORKSPACE_PINS')
        return value['revisions']

    @staticmethod
    def _manifest(value):
        if (not isinstance(value,dict) or set(value)!={'state','files','backup_id','base_revision'}
                or value['state'] not in ('prepared','complete','rolled_back','restored','purged')
                or not isinstance(value['files'],dict)
                or any(not re.fullmatch(r'(?:'+HASH+r'|archive-'+HASH+r')\.json',name) or not re.fullmatch(HASH,sha) for name,sha in value['files'].items())
                or not re.fullmatch(HASH,value['backup_id']) or not re.fullmatch(HASH,value['base_revision'])):
            raise ValueError('INVALID_RECOVERY_MANIFEST')
        return value

    def _recover_pending(self):
        self._files()
        for path in sorted((self.root/'recovery').glob('*/manifest.json')):
            manifest=self._manifest(strict_loads(path.read_bytes()))
            if manifest['state']!='prepared':continue
            for name,sha in manifest['files'].items():
                source=path.parent/name;target=self.root/name
                if source.exists():
                    if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('RECOVERY_CORRUPT')
                    if target.exists():
                        if target.read_bytes()!=source.read_bytes():raise ValueError('RECOVERY_CONFLICT')
                    else:os.replace(source,target)
            manifest['state']='rolled_back';self._json(path,manifest)

    @staticmethod
    def _references(value):
        found=set()
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('revision','source_revision','base_revision') and isinstance(item,str) and re.fullmatch(HASH,item):found.add(item)
                found.update(WorkspaceMaintenance._references(item))
        elif isinstance(value,list):
            for item in value:found.update(WorkspaceMaintenance._references(item))
        return found

    def revisions(self):
        with self.store.transaction():
            self._recover_pending();head=self.store.read()['revision'];pins=set(self._pins())
            result=[]
            for path in self.root.glob('*.json'):
                if not re.fullmatch(HASH,path.stem):continue
                snapshot=self.store.read(path.stem)
                result.append({'revision':path.stem,'current':path.stem==head,'pinned':path.stem in pins,
                    'bytes':path.stat().st_size,'source_bytes':sum(len(v.encode()) for v in snapshot['files'].values()),'saved_ns':path.stat().st_mtime_ns})
            return sorted(result,key=lambda row:(not row['current'],-row['saved_ns'],row['revision']))

    def inventory(self):
        with self.store.transaction():
            self._recover_pending();rows=self.revisions();head=self.store.read()['revision']
            categories={name:{'count':0,'bytes':0} for name in ('current','history','archives','backups','recovery','experiments','metadata')}
            for path in self._files():
                relative=path.relative_to(self.root).as_posix()
                category=('current' if relative==head+'.json' else 'history' if re.fullmatch(HASH+r'\.json',relative) else
                    'archives' if relative.startswith('archive-') else 'backups' if relative.startswith('backups/') else
                    'recovery' if relative.startswith('recovery/') else 'experiments' if relative.startswith('experiments/') else 'metadata')
                categories[category]['count']+=1;categories[category]['bytes']+=path.stat().st_size
            archives=[{'id':p.stem.removeprefix('archive-'),'revision':strict_loads(p.read_bytes())['revision'],'bytes':p.stat().st_size} for p in sorted(self.root.glob('archive-*.json'))]
            recovery=[{'id':p.parent.name,**strict_loads(p.read_bytes())} for p in sorted((self.root/'recovery').glob('*/manifest.json'))]
            total=sum(c['bytes'] for c in categories.values())
            return {'revision':head,'total_bytes':total,'warning_bytes':self.limits['warning_bytes'],'categories':categories,
                'revisions':rows,'archives':archives,'recovery':recovery,'pins':self._pins(),
                'backups':[p.name for p in sorted((self.root/'backups').glob('*.json.gz'))],'limits':self.limits}

    def pin(self,expected,revision,enabled):
        with self.store.transaction():
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            if type(enabled) is not bool:raise ValueError('INVALID_PIN')
            self.store.read(revision);pins=set(self._pins())
            if enabled:pins.add(revision)
            else:pins.discard(revision)
            if len(pins)>self.limits['max_pins']:raise ValueError('PIN_LIMIT')
            self._json(self.root/'PINS.json',{'version':1,'revisions':sorted(pins)})
            return self.inventory()

    def export(self):
        with self.store.transaction():
            self._recover_pending();entries={}
            total=0
            for path in self._files():
                name=path.relative_to(self.root).as_posix()
                if ENTRY.fullmatch(name):
                    total+=path.stat().st_size
                    if total>self.limits['max_backup_bytes']:raise ValueError('BACKUP_BYTE_LIMIT')
                    entries[name]=path.read_text(encoding='utf-8')
            for path in sorted((self.root/'recovery').glob('*/manifest.json')):
                manifest=self._manifest(strict_loads(path.read_bytes()))
                for name,sha in manifest['files'].items():
                    key=path.parent.relative_to(self.root).as_posix()+'/'+name
                    if key in entries:raw=entries[key]
                    elif (self.root/name).is_file():raw=(self.root/name).read_text()
                    else:raw=self._backing(self._backup(manifest['backup_id']),path.parent.name,name)
                    if hashlib.sha256(raw.encode()).hexdigest()!=sha:raise ValueError('RECOVERY_CORRUPT')
                    entries[key]=raw
            value={'backup_version':'1.0','head_revision':self.store.read()['revision'],'entries':entries}
            value['sha256']=digest(value);self._validate_backup(value)
            return value

    def _validate_backup(self,value):
        if (not isinstance(value,dict) or set(value)!={'backup_version','head_revision','entries','sha256'}
                or value['backup_version']!='1.0' or not isinstance(value['entries'],dict)
                or len(value['entries'])>self.limits['max_backup_files']):raise ValueError('INVALID_BACKUP')
        if digest({k:v for k,v in value.items() if k!='sha256'})!=value['sha256']:raise ValueError('BACKUP_DIGEST_MISMATCH')
        if len(json.dumps(value).encode())>self.limits['max_backup_bytes']:raise ValueError('BACKUP_BYTE_LIMIT')
        entries=value['entries']
        if not isinstance(value['head_revision'],str) or not re.fullmatch(HASH,value['head_revision']):raise ValueError('INVALID_BACKUP_HEAD')
        if value['head_revision']+'.json' not in entries:raise ValueError('BACKUP_HEAD_MISSING')
        for name,raw in entries.items():
            if not ENTRY.fullmatch(name) or not isinstance(raw,str):raise ValueError('UNSAFE_BACKUP_PATH')
            parsed=strict_loads(raw)
            filename=Path(name).name
            if re.fullmatch(HASH+r'\.json',filename) and not name.startswith('experiments/'):
                validate_files(parsed['files'],self.store.limits)
                if parsed['revision']!=filename[:-5] or digest({'files':parsed['files'],'ledger':parsed['ledger']})!=parsed['revision']:
                    raise ValueError('BACKUP_REVISION_CORRUPT')
            if name.endswith('/manifest.json'):self._manifest(parsed)
            if name=='PINS.json':
                if set(parsed)!={'version','revisions'} or parsed['version']!=1 or not isinstance(parsed['revisions'],list) or len(parsed['revisions'])>self.limits['max_pins'] or any(not isinstance(r,str) or r+'.json' not in entries for r in parsed['revisions']):raise ValueError('BACKUP_PIN_INVALID')
            if name.startswith('archive-') and parsed['revision']+'.json' not in entries:raise ValueError('BACKUP_REFERENCE_MISSING')
        for name,raw in entries.items():
            if name.endswith('/manifest.json'):
                manifest=self._manifest(strict_loads(raw));cleanup_id=Path(name).parent.name
                for filename,sha in manifest['files'].items():
                    content=self._backing(value,cleanup_id,filename)
                    if hashlib.sha256(content.encode()).hexdigest()!=sha:raise ValueError('BACKUP_RECOVERY_REFERENCE_CORRUPT')
        return value

    @staticmethod
    def _backing(backup,cleanup_id,name):
        entries=backup['entries']
        key='recovery/'+cleanup_id+'/'+name
        if key in entries:return entries[key]
        if name in entries:return entries[name]
        raise ValueError('BACKUP_RECOVERY_REFERENCE_MISSING')

    def backup(self):
        with self.store.transaction():
            value=self.export();path=self.root/'backups'/('backup-'+value['sha256']+'.json.gz')
            if not path.exists():self._atomic(path,gzip.compress(json.dumps(value,ensure_ascii=True).encode(),mtime=0))
            return {'backup_id':value['sha256'],'bytes':path.stat().st_size,'head_revision':value['head_revision']}

    def _backup(self,backup_id):
        if not isinstance(backup_id,str) or not re.fullmatch(HASH,backup_id):raise ValueError('INVALID_BACKUP_ID')
        with gzip.open(self.root/'backups'/('backup-'+backup_id+'.json.gz'),'rb') as stream:
            raw=stream.read(self.limits['max_backup_bytes']+1)
        if len(raw)>self.limits['max_backup_bytes']:raise ValueError('BACKUP_BYTE_LIMIT')
        return self._validate_backup(strict_loads(raw))

    def _plan(self,value):
        if len(self.plans)>=self.limits['max_cleanup_plans']:raise ValueError('STORAGE_PLAN_LIMIT')
        plan_id=uuid.uuid4().hex;self.plans[plan_id]=value
        return plan_id

    def preview_restore(self,value,expected):
        with self.store.transaction():
            self._validate_backup(value)
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            for name,raw in value['entries'].items():
                target=self.root/name
                if target.exists() and target.read_text()!=raw and name!='PINS.json':
                    if not name.endswith('/manifest.json'):raise ValueError('BACKUP_RESTORE_CONFLICT: '+name)
                    old=self._manifest(strict_loads(target.read_bytes()));incoming=self._manifest(strict_loads(raw))
                    if old['files']!=incoming['files'] or old['base_revision']!=incoming['base_revision']:raise ValueError('BACKUP_RESTORE_CONFLICT: '+name)
            plan_id=self._plan({'kind':'restore','expected':expected,'backup':copy.deepcopy(value)})
            incoming=strict_loads(value['entries'][value['head_revision']+'.json'])
            return {'plan_id':plan_id,'kind':'restore','base_revision':expected,'incoming_revision':incoming['revision'],
                'files':sorted(incoming['files']),'entries':len(value['entries']),
                'changes':[{'path':name,'current':self.store.read()['files'].get(name),'incoming':incoming['files'].get(name)} for name in sorted(set(self.store.read()['files'])|set(incoming['files'])) if self.store.read()['files'].get(name)!=incoming['files'].get(name)],'message':'确认后保留当前项目的完整备份，导入历史并原子切换HEAD；当前源码不会被静默替换。'}

    def apply_restore(self,plan_id,expected):
        with self.store.transaction():
            plan=self.plans.get(plan_id)
            if not plan or plan['kind']!='restore' or plan['expected']!=expected or self.store.read()['revision']!=expected:raise ValueError('STALE_STORAGE_PLAN')
            value=plan['backup'];self.backup()  # A recoverable copy exists before publishing any imported data.
            imported_path=self.root/'backups'/('backup-'+value['sha256']+'.json.gz')
            if not imported_path.exists():self._atomic(imported_path,gzip.compress(json.dumps(value,ensure_ascii=True).encode(),mtime=0))
            for name,raw in value['entries'].items():
                if name=='PINS.json' or name.endswith('/manifest.json'):continue
                path=self.root/name
                if path.exists():
                    if path.read_text()!=raw:raise ValueError('BACKUP_RESTORE_CONFLICT: '+name)
                else:self._atomic(path,raw.encode())
            for name,raw in value['entries'].items():
                if name.endswith('/manifest.json'):
                    manifest=self._manifest(strict_loads(raw));manifest['backup_id']=value['sha256']
                    if manifest['state']=='purged':manifest['state']='complete'
                    self._json(self.root/name,manifest)
            incoming_pins=strict_loads(value['entries']['PINS.json'])['revisions'] if 'PINS.json' in value['entries'] else []
            pins=sorted(set(self._pins())|set(incoming_pins))
            if len(pins)>self.limits['max_pins']:raise ValueError('PIN_LIMIT')
            for revision in pins:self.store.read(revision)
            self._json(self.root/'PINS.json',{'version':1,'revisions':pins})
            incoming=strict_loads(value['entries'][value['head_revision']+'.json'])
            result=self.store._write(incoming['files'],incoming['ledger'])
            self.plans.pop(plan_id,None)
            return result

    def _fingerprint(self):
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.json')}
        files.update({p.relative_to(self.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root/'experiments').glob('*.json')})
        return digest({'files':files,'protected':sorted(getattr(self.store,'protected_revisions',set()))})

    def cleanup_plan(self,expected,keep_recent,archive_ids):
        with self.store.transaction():
            self._recover_pending()
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            if type(keep_recent) is not int or not 0<=keep_recent<=10000 or not isinstance(archive_ids,list):raise ValueError('INVALID_RETENTION_POLICY')
            available={p.stem.removeprefix('archive-'):p for p in self.root.glob('archive-*.json')}
            if any(not isinstance(i,str) or i not in available for i in archive_ids):raise ValueError('INVALID_ARCHIVE_SELECTION')
            protected={expected:'current',**{r:'pinned' for r in self._pins()},**{r:'deployment' for r in getattr(self.store,'protected_revisions',set())}}
            rows=self.revisions()
            for row in sorted(rows,key=lambda row:-row['saved_ns'])[:keep_recent]:protected.setdefault(row['revision'],'recent')
            for archive_id,path in available.items():
                if archive_id not in archive_ids:
                    for r in self._references(strict_loads(path.read_bytes())):protected.setdefault(r,'archive_reference')
            for path in (self.root/'experiments').glob('*.json'):
                for r in self._references(strict_loads(path.read_bytes())):protected.setdefault(r,'experiment_reference')
            for pending in self.store.plans.values():
                for r in self._references(pending):protected.setdefault(r,'template_plan')
            names=[r['revision']+'.json' for r in rows if r['revision'] not in protected]
            names+=['archive-'+i+'.json' for i in archive_ids]
            candidates={name:hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in names}
            plan={'kind':'cleanup','expected':expected,'fingerprint':self._fingerprint(),'files':candidates}
            plan_id=self._plan(plan)
            return {'plan_id':plan_id,'kind':'cleanup','base_revision':expected,'files':names,'protected':protected,
                'recyclable_bytes':sum((self.root/name).stat().st_size for name in names),
                'message':'确认后先生成压缩备份，再移入可恢复区。回收区仍占空间；永久清空需另行明确操作。'}

    def cleanup_apply(self,plan_id,expected):
        with self.store.transaction():
            plan=self.plans.get(plan_id)
            if not plan or plan['kind']!='cleanup' or plan['expected']!=expected or self.store.read()['revision']!=expected or plan['fingerprint']!=self._fingerprint():raise ValueError('STALE_STORAGE_PLAN')
            backup=self.backup();folder=self.root/'recovery'/plan_id
            manifest={'state':'prepared','files':plan['files'],'backup_id':backup['backup_id'],'base_revision':expected}
            self._json(folder/'manifest.json',manifest)
            for name in plan['files']:os.replace(self.root/name,folder/name)
            manifest['state']='complete';self._json(folder/'manifest.json',manifest)
            self.plans.pop(plan_id,None)
            return self.inventory()

    def restore_cleanup(self,cleanup_id,expected):
        with self.store.transaction():
            self._recover_pending()
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            if not re.fullmatch(r'[a-f0-9]{32}',cleanup_id):raise ValueError('INVALID_CLEANUP_ID')
            folder=self.root/'recovery'/cleanup_id;manifest=self._manifest(strict_loads((folder/'manifest.json').read_bytes()))
            for name,sha in manifest['files'].items():
                source=folder/name;target=self.root/name
                raw=source.read_bytes() if source.exists() else self._backing(self._backup(manifest['backup_id']),cleanup_id,name).encode()
                if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('RECOVERY_CORRUPT')
                if target.exists() and target.read_bytes()!=raw:raise ValueError('RECOVERY_CONFLICT')
                if not target.exists():self._atomic(target,raw)
            manifest['state']='restored';self._json(folder/'manifest.json',manifest)
            return self.inventory()

    def purge_recovery(self,cleanup_id,expected):
        with self.store.transaction():
            self._recover_pending()
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            if not re.fullmatch(r'[a-f0-9]{32}',cleanup_id):raise ValueError('INVALID_CLEANUP_ID')
            folder=self.root/'recovery'/cleanup_id;manifest=self._manifest(strict_loads((folder/'manifest.json').read_bytes()));backup=self._backup(manifest['backup_id'])
            for name,sha in manifest['files'].items():
                if hashlib.sha256(self._backing(backup,cleanup_id,name).encode()).hexdigest()!=sha:raise ValueError('RECOVERY_BACKUP_MISSING')
            for name in manifest['files']:(folder/name).unlink(missing_ok=True)
            manifest['state']='purged';self._json(folder/'manifest.json',manifest)
            return self.inventory()

    def experiment_save(self,package,validator):
        from .engineering import settings
        limits=settings()['lab']
        validator.structure(package,'experiment-package.schema.json')
        raw=json.dumps(package,ensure_ascii=True,allow_nan=False).encode()
        if len(raw)>self.store.limits['max_source_bytes']*4:raise ValueError('EXPERIMENT_SAVE_LIMIT: 请导出记录到文件')
        with self.store.transaction():
            folder=self.root/'experiments';record_id=digest(package);path=folder/(record_id+'.json')
            if not path.exists():
                if len(list(folder.glob('*.json')))>=limits['max_saved_records']:raise ValueError('EXPERIMENT_STORAGE_LIMIT: 请先导出记录')
                self._atomic(path,raw)
            return {'id':record_id,'bytes':path.stat().st_size}

    def experiment_list(self):
        with self.store.transaction():
            return [{'id':path.stem,'bytes':path.stat().st_size,'frames':len(strict_loads(path.read_bytes())['record']['frames'])}
                for path in sorted((self.root/'experiments').glob('*.json'))]

    def experiment_load(self,record_id):
        if not isinstance(record_id,str) or not re.fullmatch(HASH,record_id):raise ValueError('INVALID_EXPERIMENT_ID')
        with self.store.transaction():
            path=self.root/'experiments'/(record_id+'.json')
            if path.stat().st_size>self.store.limits['max_source_bytes']*4:raise ValueError('EXPERIMENT_SAVE_LIMIT')
            value=strict_loads(path.read_bytes())
            if digest(value)!=record_id:raise ValueError('EXPERIMENT_RECORD_CORRUPT')
            return value

    def _backup_fingerprint(self):
        return digest({'backups':[(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted((self.root/'backups').glob('*.json.gz'))],
            'recovery':{p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((self.root/'recovery').glob('*/manifest.json'))}})

    def backup_cleanup_plan(self,expected,backup_ids):
        with self.store.transaction():
            self._recover_pending()
            if self.store.read()['revision']!=expected:raise ValueError('REVISION_CONFLICT')
            available={p.name.removeprefix('backup-').removesuffix('.json.gz'):p for p in (self.root/'backups').glob('backup-*.json.gz')}
            if not isinstance(backup_ids,list) or len(set(backup_ids))!=len(backup_ids) or any(i not in available for i in backup_ids):raise ValueError('INVALID_BACKUP_SELECTION')
            protected={self._manifest(strict_loads(p.read_bytes()))['backup_id'] for p in (self.root/'recovery').glob('*/manifest.json')}
            if available:protected.add(max(available,key=lambda key:available[key].stat().st_mtime_ns))
            if set(backup_ids)&protected:raise ValueError('BACKUP_IS_REFERENCED_OR_LATEST')
            plan_id=self._plan({'kind':'backup_cleanup','expected':expected,'ids':backup_ids,'fingerprint':self._backup_fingerprint()})
            return {'plan_id':plan_id,'kind':'backup_cleanup','base_revision':expected,'files':[available[i].name for i in backup_ids],
                'protected':sorted(protected),'recyclable_bytes':sum(available[i].stat().st_size for i in backup_ids),
                'message':'永久删除所选未引用的旧压缩备份。最新备份和所有恢复区引用均保护；当前/历史源码不受影响。'}

    def backup_cleanup_apply(self,plan_id,expected):
        with self.store.transaction():
            plan=self.plans.get(plan_id)
            if not plan or plan['kind']!='backup_cleanup' or plan['expected']!=expected or self.store.read()['revision']!=expected or plan['fingerprint']!=self._backup_fingerprint():raise ValueError('STALE_STORAGE_PLAN')
            for key in plan['ids']:(self.root/'backups'/('backup-'+key+'.json.gz')).unlink()
            self.plans.pop(plan_id,None)
            return self.inventory()
