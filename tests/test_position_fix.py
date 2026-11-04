"""Projected position input contract, separate from legacy intercepted target GPS."""
import copy
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','runtime')]
from tankbot import Inputs,Module,ModuleContext,Pose2D,PositionFix2D
from tankbot_host.authority import load_config
from tankbot_protocol.validation import Validator,Rejected,envelope
from module_runner import ModuleRunner


class PositionFixTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/game.yaml')

    def message(self):
        return envelope('position_fix2d@1','/robot/sensors/gps/fix',
                        {'position_m':[1.,2.],'covariance':[1.,0.,0.,1.]},
                        tick=6,hz=60,run_id='position-test',publisher_id='sensor:gps',
                        sequence=0,frame_id='map')

    def test_schema_covariance_frame_and_publisher_grants(self):
        message=self.message();validator=Validator(self.config,'position-test')
        grants={('sensor:gps','/robot/sensors/gps/fix','position_fix2d@1','map')}
        validator.validate(message,now=6,grants=grants,consume=False)
        for covariance in ([1.,2.,2.,1.],[-1.,0.,0.,1.],[1.,.5,0.,1.]):
            bad=copy.deepcopy(message);bad['payload']['covariance']=covariance
            with self.subTest(covariance=covariance),self.assertRaises(Rejected):
                validator.validate(bad,now=6,grants=grants,consume=False)
        with self.assertRaisesRegex(Rejected,'UNAUTHORIZED'):
            validator.validate(message,now=6,grants=set())
        bad=copy.deepcopy(message);bad['frame_id']='base_link'
        with self.assertRaisesRegex(Rejected,'INVALID_FRAME'):
            validator.validate(bad,now=6,grants=grants)

    def test_sdk_arrays_are_typed_owned_and_read_only(self):
        source=np.array([1.,2.],dtype=np.float64)
        fix=PositionFix2D(source,np.eye(2,dtype=np.float64))
        source[0]=99.
        self.assertEqual(fix.position_m[0],1.)
        self.assertEqual(fix.covariance.shape,(2,2))
        for array in (fix.position_m,fix.covariance):
            self.assertEqual(array.dtype,np.float64)
            with self.assertRaises(ValueError):array.setflags(write=True)
        for values in ([1.,float('nan')],[1.,2.,3.]):
            with self.assertRaises(ValueError):PositionFix2D(values,np.eye(2))
        with self.assertRaises(TypeError):PositionFix2D(['1','2'],np.eye(2))
        with self.assertRaises(ValueError):PositionFix2D([1.,2.],None)
        with self.assertRaises(TypeError):ModuleContext(6,.1,12,{}).publish('fix',fix,frame_id='map')

    def test_runner_decodes_typed_sample_and_preserves_observation_time(self):
        class Probe(Module):
            def update(self,inputs:Inputs,ctx:ModuleContext)->None:
                sample=inputs.latest('gps')
                self.fix=sample
                assert isinstance(sample.data,PositionFix2D)
                ctx.publish('pose',Pose2D(float(sample.data.position_m[0]),float(sample.data.position_m[1]),0.),
                            frame_id='map',simulation_tick=sample.simulation_tick)
        runner=object.__new__(ModuleRunner)
        runner.init={'config':{},'physics_hz':60,'run_id':'position-test','publisher_id':'module:probe',
                     'input_channels':{'gps':'/robot/sensors/gps/fix'},'output_channels':{'pose':'/robot/estimates/probe/pose'}}
        runner.contract={'module_id':'probe','outputs':{'pose':{'schema':'pose2d@1'}}}
        runner.init['contract']=runner.contract;runner.sequence=0;runner.module=Probe()
        request={'payload':{'activation_tick':6,'output_commit_tick':12,'step_id':'step-6',
                            'modules':[{'module_id':'probe','dt_ticks':6}],'inputs':[self.message()]}}
        response=runner.step(request)
        self.assertEqual(runner.module.fix.simulation_tick,6)
        self.assertEqual(runner.module.fix.frame_id,'map')
        self.assertEqual(response['payload']['outputs'][0]['simulation_tick'],6)
        self.assertEqual(response['payload']['outputs'][0]['payload']['x_m'],1.)
