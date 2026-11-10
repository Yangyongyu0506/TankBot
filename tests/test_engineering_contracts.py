"""Public engineering artifacts and message adapters remain compatible and bounded."""
import json
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import ModuleContext,Twist,Vector3,WheelVoltage
from tankbot.messages import decode_message,OUTPUT_SCHEMAS
from tankbot_host.authority import load_config
from tankbot_protocol.validation import Validator,Rejected


class EngineeringContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.validator=Validator(load_config(ROOT/'config/game.yaml'),'contracts')

    def test_examples_and_old_runtime_results_have_valid_formal_schemas(self):
        for name,schema in [('engineering-settings','engineering'),('workspace-backup','workspace-backup'),('experiment-empty-record','experiment'),('experiment-empty-package','experiment-package'),('runtime-execution-profiles','runtime-execution')]:
            with self.subTest(name=name):self.validator.structure(json.loads((ROOT/'docs/examples'/ (name+'.json')).read_text()),schema+'.schema.json')
        sample=json.loads((ROOT/'docs/examples/runtime-telemetry.json').read_text())
        self.assertTrue(self.validator.schemas['payloads.schema.json'].evolve(schema={'$ref':'#/$defs/runtime_step_result'}).is_valid(sample))
        old={k:v for k,v in sample.items() if k!='telemetry'}
        self.assertTrue(self.validator.schemas['payloads.schema.json'].evolve(schema={'$ref':'#/$defs/runtime_step_result'}).is_valid(old))

    def test_shared_message_registry_preserves_twist_and_voltage_wire_shapes(self):
        context=ModuleContext(6,.1,12,{})
        context.publish('cmd',Twist(Vector3(x=.2),Vector3(z=.3)),frame_id='base_link')
        port,schema,payload,frame,tick=context._outputs[0]
        self.assertEqual(schema,'twist@1');self.assertEqual(decode_message(schema,payload),Twist(Vector3(x=.2),Vector3(z=.3)))
        self.assertEqual(OUTPUT_SCHEMAS[WheelVoltage],'wheel_voltage@1')
        self.assertEqual(decode_message('wheel_voltage@1',{'left_voltage_v':1.,'right_voltage_v':2.}),WheelVoltage(1.,2.))

    def test_optional_diagnostics_reject_non_finite_wrong_shape_and_missing_grants(self):
        policy={'diagnostic_policy':{'channels':{'innovation':2},'max_events':1}}
        for value in ([1.],np.array([np.nan,0.]),[True,False],['x','y']):
            with self.subTest(value=str(value)),self.assertRaises(ValueError):ModuleContext(0,0.,0,policy).diagnostic('innovation',value)
        with self.assertRaises(PermissionError):ModuleContext(0,0.,0,{}).diagnostic('innovation',[0.,0.])

    def test_course_diagnostic_declaration_obeys_configured_engineering_limit(self):
        from tankbot_host.engineering import settings
        from tankbot_host.level_plugins import _validate,read_definition,LevelValidationError
        config=load_config(ROOT/'config/game.yaml')
        value=read_definition(ROOT/'levels/weapons.C2.yaml',config['level_plugins']['limits'])
        limits=copy.deepcopy(settings());limits['lab']['diagnostic_max_values']=1
        with patch('tankbot_host.engineering.settings',return_value=limits):
            with self.assertRaisesRegex(LevelValidationError,'evaluation.experiment.diagnostics.innovation'):
                _validate(value,'weapons.C2.yaml',config,self.validator)
