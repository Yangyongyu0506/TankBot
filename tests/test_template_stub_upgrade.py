"""Existing projects upgrade untouched generated algorithms through an explicit preview."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.workspace import starter
from tankbot_host.workspace_api import WorkspaceAPI

PATH='perception/polar_tracker.py'
OLD='''import numpy as np
from numpy.typing import NDArray
from tankbot import PolarTargetEstimate

class PolarTracker:
    def __init__(self, measurement_covariance: NDArray[np.float64]) -> None:
        self.measurement_covariance: NDArray[np.float64] = measurement_covariance
        self.estimate: PolarTargetEstimate | None = None

    def update(self, measurements_rt: NDArray[np.float64], own_pose: NDArray[np.float64],
               dt: float) -> PolarTargetEstimate | None:
        # TODO: algorithm
        return self.estimate
'''


class GeneratedAlgorithmUpgradeTests(unittest.TestCase):
    def test_lesson_help_only_changes_do_not_force_algorithm_replacement(self):
        from tankbot_host.campaign_templates import generated_algorithm_updates
        config=configure(load_config(ROOT/'config/game.yaml'),'c3')
        files=starter(config)
        source=files[PATH].replace('"""','"""Additional lesson help. ',1)
        files[PATH]=source
        ledger={'campaign-c3-unlock':{'files':{PATH:source}}}
        self.assertEqual(generated_algorithm_updates(config,files,ledger),[])

    def project(self,folder,level):
        config=configure(load_config(ROOT/'config/game.yaml'),level)
        api=WorkspaceAPI(config,directory=folder)
        before=api.store.read();old=starter(config);old[PATH]=OLD
        plan=api.store.plan('campaign-'+level+'-unlock','3.0.0',old,before['revision'])
        saved=api.store.apply(plan['plan_id'],before['revision'],{p:'incoming' for p in old})
        return api,saved

    def test_current_adapter_with_old_untouched_algorithm_offers_preview_and_preserves_history(self):
        for level in ('c3','c4'):
            with self.subTest(level=level),tempfile.TemporaryDirectory() as folder:
                api,_=self.project(folder,level)
                saved=api.store.read()
                authored={'perception/transforms.py':'# player C1 code stays byte-for-byte\n',
                          'perception/tracker.py':'# player C2 KF code stays byte-for-byte\n'}
                saved=api.store.edit(saved['revision'],authored)
                view=api.get();self.assertTrue(view['learning']['upgrade_required'])
                self.assertEqual(view['learning']['upgrade']['generated_algorithm_files'],[PATH])
                plan=api.post('upgrade',{'revision':saved['revision']})
                self.assertEqual(api.store.read()['revision'],saved['revision'],'preview never writes source')
                self.assertEqual(plan['generated_algorithm_files'],[PATH])
                entries={e['path']:e for e in plan['entries']}
                self.assertEqual(entries[PATH]['current'],OLD)
                self.assertIn('tuple[PolarTargetEstimate, ...]',entries[PATH]['incoming'])
                for path in authored:self.assertNotIn(path,entries)
                updated=api.post('apply',{'plan_id':plan['plan_id'],'revision':saved['revision'],
                    'resolutions':{e['path']:'incoming' for e in plan['entries']}})
                self.assertFalse(api.get()['learning']['upgrade_required'])
                self.assertEqual(api.store.read(saved['revision'])['files'][PATH],OLD)
                for path,source in authored.items():self.assertEqual(updated['files'][path],source)
                self.assertFalse(WorkspaceAPI(api.config,directory=folder).get()['learning']['upgrade_required'])

    def test_authored_algorithm_and_untracked_code_are_never_offered_for_replacement(self):
        for level in ('c3','c4'):
            with self.subTest(level=level),tempfile.TemporaryDirectory() as folder:
                api,_=self.project(folder,level)
                saved=api.store.read();source=OLD+'\n# player changes, even one comment, must be preserved\n'
                saved=api.store.edit(saved['revision'],{PATH:source})
                self.assertFalse(api.get()['learning']['upgrade_required'])
                plan=api.post('upgrade',{'revision':saved['revision']})
                self.assertNotIn(PATH,[e['path'] for e in plan['entries']])
                self.assertEqual(api.store.read()['files'][PATH],source)
                # A TODO or matching signature alone never proves generated ownership.
                from tankbot_host.campaign_templates import generated_algorithm_updates
                self.assertEqual(generated_algorithm_updates(api.config,{PATH:OLD},{}),[])


if __name__=='__main__':unittest.main()
