"""Player history can be previewed, pinned, backed up and recovered without silent deletion."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import load_config
from tankbot_host.workspace import WorkspaceStore,digest,_migrate_store
from tankbot_host.workspace_maintenance import WorkspaceMaintenance


class WorkspaceMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.limits=load_config(ROOT/'config/game.yaml')['workspace']
        self.store=WorkspaceStore(self.root/'project',{'main.py':'VALUE: int = 0\n'},self.limits)
        self.m=WorkspaceMaintenance(self.store);self.revisions=[self.store.read()['revision']]
        for i in range(1,6):self.revisions.append(self.store.edit(self.store.read()['revision'],{'main.py':f'VALUE: int = {i}\n'})['revision'])

    def test_backup_restore_preserves_every_revision_and_archives_and_uses_explicit_cas(self):
        oldest=self.revisions[0];head=self.revisions[-1]
        self.store.archive(oldest,{'kind':'test','status':'Ready'})
        self.m.pin(head,oldest,True)
        exported=self.m.export();self.m.backup()
        newer=self.store.edit(head,{'main.py':'VALUE: int = 99\n'})['revision']
        plan=self.m.preview_restore(exported,newer)
        self.assertEqual(self.store.read()['revision'],newer)
        self.assertEqual(plan['incoming_revision'],head);self.assertTrue(plan['changes'])
        self.m.apply_restore(plan['plan_id'],newer)
        self.assertEqual(self.store.read()['revision'],head)
        self.assertEqual(self.store.read(newer)['files']['main.py'],'VALUE: int = 99\n')
        for revision in self.revisions:self.assertEqual(self.store.read(revision)['revision'],revision)
        self.assertEqual(self.m._pins(),[oldest]);self.assertEqual(len(self.store.archives()),1)
        with self.assertRaisesRegex(ValueError,'STALE_STORAGE_PLAN'):self.m.apply_restore(plan['plan_id'],newer)

    def test_cleanup_keeps_head_pins_deployment_and_archive_references_and_recovers(self):
        head=self.revisions[-1];self.m.pin(head,self.revisions[0],True)
        self.store.protected_revisions={self.revisions[1]};self.store.archive(self.revisions[2],{'kind':'deploy'})
        before=self.m.inventory();plan=self.m.cleanup_plan(head,0,[])
        self.assertEqual(set(plan['files']),{r+'.json' for r in self.revisions[3:-1]})
        self.assertEqual(before,self.m.inventory())
        self.m.cleanup_apply(plan['plan_id'],head)
        self.assertEqual(self.store.read()['revision'],head)
        self.assertTrue((self.store.directory/'backups').is_dir())
        for revision in self.revisions[:3]:self.store.read(revision)
        self.m.restore_cleanup(plan['plan_id'],head)
        for revision in self.revisions:self.store.read(revision)

    def test_archive_recycling_is_explicit_and_purge_requires_a_verified_backup(self):
        head=self.revisions[-1];archive=self.store.archive(self.revisions[0],{'kind':'test'})['archive_id']
        plan=self.m.cleanup_plan(head,0,[archive]);self.m.cleanup_apply(plan['plan_id'],head)
        inventory=self.m.inventory();item=next(r for r in inventory['recovery'] if r['id']==plan['plan_id'])
        backup=self.store.directory/'backups'/('backup-'+item['backup_id']+'.json.gz')
        raw=backup.read_bytes();backup.write_bytes(b'corrupt')
        with self.assertRaises((ValueError,OSError,EOFError)):self.m.purge_recovery(plan['plan_id'],head)
        self.assertTrue((self.store.directory/'recovery'/plan['plan_id']/(self.revisions[0]+'.json')).exists())
        backup.write_bytes(raw);self.m.purge_recovery(plan['plan_id'],head)
        self.assertEqual(self.m.inventory()['recovery'][0]['state'],'purged')
        self.m.restore_cleanup(plan['plan_id'],head)  # Rehydrates from the verified compressed backup.
        self.assertEqual(self.store.read(self.revisions[0])['revision'],self.revisions[0])
        self.assertEqual(len(self.store.archives()),1)

    def test_new_edit_or_changed_protection_invalidates_preview(self):
        head=self.revisions[-1];plan=self.m.cleanup_plan(head,0,[])
        self.store.protected_revisions={self.revisions[0]}
        with self.assertRaisesRegex(ValueError,'STALE_STORAGE_PLAN'):self.m.cleanup_apply(plan['plan_id'],head)
        plan=self.m.cleanup_plan(head,0,[])
        self.store.edit(head,{'main.py':'VALUE: int = 9\n'})
        with self.assertRaisesRegex(ValueError,'STALE_STORAGE_PLAN'):self.m.cleanup_apply(plan['plan_id'],head)

    def test_export_after_purge_is_self_contained_on_another_machine(self):
        head=self.revisions[-1];plan=self.m.cleanup_plan(head,0,[])
        self.m.cleanup_apply(plan['plan_id'],head);self.m.purge_recovery(plan['plan_id'],head)
        exported=self.m.export()
        other=WorkspaceStore(self.root/'other',{'main.py':'OTHER: int = 0\n'},self.limits)
        maintenance=WorkspaceMaintenance(other);expected=other.read()['revision']
        preview=maintenance.preview_restore(exported,expected)
        maintenance.apply_restore(preview['plan_id'],expected)
        maintenance.restore_cleanup(plan['plan_id'],head)
        for revision in self.revisions:self.assertEqual(other.read(revision),self.store.read(revision) if (self.store.directory/(revision+'.json')).exists() else json.loads(exported['entries']['recovery/'+plan['plan_id']+'/'+revision+'.json']))
        maintenance.purge_recovery(plan['plan_id'],head)

    def test_interrupted_move_rolls_back_on_reopen_and_head_never_changes(self):
        head=self.revisions[-1];plan=self.m.cleanup_plan(head,0,[])
        import os
        replace=os.replace;count=0
        def interrupt(source,target):
            nonlocal count
            if Path(source).parent==self.store.directory and Path(source).suffix=='.json' and len(Path(source).stem)==64:
                count+=1
                if count==2:raise OSError('simulated interruption')
            return replace(source,target)
        with patch('tankbot_host.workspace_maintenance.os.replace',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'simulated interruption'):self.m.cleanup_apply(plan['plan_id'],head)
        reopened=WorkspaceStore(self.store.directory,{'main.py':''},self.limits)
        inventory=WorkspaceMaintenance(reopened).inventory()
        self.assertEqual(inventory['revision'],head)
        for revision in self.revisions:reopened.read(revision)
        self.assertEqual(inventory['recovery'][0]['state'],'rolled_back')

    def test_backup_rejects_path_traversal_and_recovery_manifest_escape(self):
        backup=self.m.export();bad=copy.deepcopy(backup)
        bad['entries']['../outside.json']='{}';bad['sha256']=digest({k:v for k,v in bad.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'UNSAFE_BACKUP_PATH'):self.m.preview_restore(bad,self.revisions[-1])
        bad=copy.deepcopy(backup);bad['entries']['recovery/'+'a'*32+'/manifest.json']=json.dumps({'state':'prepared','files':{'../outside':'a'*64},'backup_id':'b'*64,'base_revision':self.revisions[-1]});bad['sha256']=digest({k:v for k,v in bad.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'INVALID_RECOVERY_MANIFEST'):self.m.preview_restore(bad,self.revisions[-1])

    def test_existing_migration_copies_backups_pins_and_recovery_byte_for_byte(self):
        head=self.revisions[-1];self.m.pin(head,self.revisions[0],True);self.m.backup()
        destination=self.root/'migrated';_migrate_store(self.store.directory,destination,{'main.py':''},self.limits)
        self.assertEqual((destination/'HEAD.json').read_bytes(),self.store.head.read_bytes())
        for source in self.store.directory.rglob('*'):
            if source.is_file() and source.name!='LOCK':self.assertEqual(source.read_bytes(),(destination/source.relative_to(self.store.directory)).read_bytes())

    def test_redundant_backups_need_a_preview_and_latest_and_referenced_are_protected(self):
        head=self.revisions[-1];first=self.m.backup()
        self.m.pin(head,self.revisions[0],True);second=self.m.backup()
        with self.assertRaisesRegex(ValueError,'REFERENCED_OR_LATEST'):self.m.backup_cleanup_plan(head,[second['backup_id']])
        plan=self.m.backup_cleanup_plan(head,[first['backup_id']])
        self.assertEqual(len(self.m.inventory()['backups']),2)
        self.m.backup_cleanup_apply(plan['plan_id'],head)
        self.assertEqual(len(self.m.inventory()['backups']),1)
        for revision in self.revisions:self.store.read(revision)
