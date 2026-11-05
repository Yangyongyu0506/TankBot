"""Structural hot-path dispatch must agree with the unmodified JSON Schema validator."""
import copy
import json
from pathlib import Path
import sys
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry,Resource

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_protocol.validation import Validator,_StructuralValidator
from tankbot_protocol.conformance import cases


class ValidationDispatchTests(unittest.TestCase):
    def test_all_protocol_fixtures_and_mutations_match_standard_validator(self):
        optimized=Validator({},'comparison')._envelope_validator
        sources=[json.loads(p.read_text()) for p in (ROOT/'docs/schemas').glob('*.schema.json')]
        registry=Registry().with_resources((s['$id'],Resource.from_contents(s)) for s in sources)
        standard=Draft202012Validator(json.loads((ROOT/'docs/schemas/envelope.schema.json').read_text()),registry=registry)
        checked=0
        for case in cases(ROOT/'docs/examples'):
            value=case['message'];variants=[value]
            for field in ('schema','message_type','channel','frame_id','payload','simulation_tick'):
                for replacement in (None,False,[],{},'unknown',-1):
                    changed=copy.deepcopy(value);changed[field]=replacement;variants.append(changed)
                changed=copy.deepcopy(value);changed.pop(field,None);variants.append(changed)
            for changed in variants:
                self.assertEqual(optimized.is_valid(changed),standard.is_valid(changed),(case['id'],changed))
                checked+=1
        self.assertGreater(checked,2000)

    def test_missing_tags_else_and_unconditional_siblings_keep_standard_semantics(self):
        schemas=[
            {'allOf':[{'if':{'properties':{'schema':{'const':'a'}}},'then':{'required':['payload']}}]},
            {'allOf':[{'if':{'properties':{'schema':{'const':'a'}}},'then':{'required':['payload']},'else':{'required':['other']}}]},
            {'allOf':[{'if':{'properties':{'schema':{'const':'a'}}},'then':{'required':['payload']},'required':['other']}]},
            {'allOf':[{'if':{'properties':{'schema':{'const':'a'},'channel':{'const':'b'}}},'then':False}]},
        ]
        for schema in schemas:
            for value in ({},{'schema':'a'},{'schema':'b'},{'schema':'b','other':1},False,[],None):
                with self.subTest(schema=schema,value=value):
                    self.assertEqual(_StructuralValidator(schema).is_valid(value),Draft202012Validator(schema).is_valid(value))
