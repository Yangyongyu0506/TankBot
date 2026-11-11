"""Optional-input zero-reference protection and sample-time contract, no world needed."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('sdk/python','protocol','host','tests')]
from tankbot import (Inputs,Sample,Pose2D,JointState,Scan2D,ModuleContext,Twist,Vector3)


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        follower=types.ModuleType('navigation.path_follower');local=types.ModuleType('navigation.local_controller')
        class Follower:
            def __init__(self,*args):pass
            def update(self,*args):return Twist(Vector3(x=.4))
        self.calls=[]
        calls=self.calls
        class Controller:
            def __init__(self,*args):self.parameters=args
            def update(self,observation,dt):calls.append((observation,dt));return Twist(Vector3(x=.2))
        follower.PathFollower=Follower;local.LocalController=Controller
        with patch.dict(sys.modules,{'navigation':types.ModuleType('navigation'),'navigation.path_follower':follower,'navigation.local_controller':local}):
            spec=importlib.util.spec_from_file_location('isolated_local',ROOT/'templates/navigation/local_module.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.module=module.LocalNavigationModule()
        from tankbot_host.authority import load_config
        from tankbot_host.campaign import configure
        from tankbot_host.navigation import drive_parameters
        self.config={'path_tracking_parameters':{'reference':{'points_m':[[0.,0.],[1.,0.]]},'control_limits':{'min_vx_mps':0.,'max_vx_mps':.5,'max_wz_radps':1.5},'reference_speed_mps':.4,'position_tolerance_m':.35},'local_navigation_parameters':{'input_max_age_ticks':12,'tick_duration_s':1/60,'robot_radius_m':.5,'safety_margin_m':.15,'command_delay_s':.2},'drive_parameters':drive_parameters(configure(load_config(ROOT/'config/game.yaml'),'navigation.c6'))}
        self.module.setup(ModuleContext(0,.1,6,self.config))

    def inputs(self,tick=12):
        scan=Scan2D(np.full(180,6.),np.zeros(180,dtype=bool),0.,np.pi/90,.05,6.,.02,tick)
        return {'pose':Sample(Pose2D(0,0,0),tick,'map',1),
                'scan':Sample(scan,tick,'base_link',1),
                'wheels':Sample(JointState(('left','right'),(0.,0.),(0.,0.)),tick,'base_link',1)}

    def call(self,samples,tick=24):
        ctx=ModuleContext(tick,.1,tick+6,self.config);self.module.update(Inputs(samples),ctx);return ctx._outputs

    def test_exact_age_limit_calls_controller_with_immutable_raw_sample_inputs(self):
        outputs=self.call(self.inputs())
        self.assertEqual(len(self.calls),1);o,dt=self.calls[0]
        self.assertEqual(dt,.1);self.assertEqual(o.pose_age_s,.2);self.assertEqual(o.scan_age_s,.2)
        self.assertEqual(o.scan.sample_tick,12);self.assertEqual(outputs[0][2]['linear']['x'],.2)
        self.assertEqual(outputs[1][2]['protection'],'ok');self.assertEqual(outputs[1][2]['nominal_vx_mps'],.4)
        for array in (o.estimated_pose,o.reference_path,o.wheel_rates_radps):
            with self.assertRaises(ValueError):array.setflags(write=True)

    def test_missing_stale_frame_no_nominal_fallback_and_recovery(self):
        for port in ('pose','scan','wheels'):
            for error in ('missing','stale','frame'):
                with self.subTest(port=port,error=error):
                    values=self.inputs();old=values[port]
                    if error=='missing':values.pop(port)
                    elif error=='stale':values[port]=Sample(old.data,11,old.frame_id,old.sequence_number)
                    else:values[port]=Sample(old.data,12,'wrong',old.sequence_number)
                    before=len(self.calls);outputs=self.call(values)
                    self.assertEqual(len(self.calls),before);self.assertEqual(outputs[0][2],{'linear':{'x':0.,'y':0.,'z':0.},'angular':{'x':0.,'y':0.,'z':0.}})
                    self.assertNotEqual(outputs[1][2]['protection'],'ok')
        self.call(self.inputs());self.assertEqual(len(self.calls),1)

    def test_reverse_rejected_and_final_limits(self):
        with patch.object(self.module.controller,'update',return_value=Twist(Vector3(x=-.01))):
            with self.assertRaisesRegex(ValueError,'倒车'):self.call(self.inputs())
        with patch.object(self.module.controller,'update',return_value=Twist(Vector3(x=9.),Vector3(z=9.))):
            output=self.call(self.inputs())[0][2];self.assertEqual(output['linear']['x'],.5);self.assertEqual(output['angular']['z'],1.5)
