"""Portable guard tests only; these do not simulate/claim any Mac acceptance."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest

BASE = Path(__file__).resolve().parent

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

phased = module('phased_guards', BASE / 'run_installed_readiness_phased.py')
accepted = module('accepted_guards', BASE / 'installed-launch-01/run_installed_launch.py')

class Guards(unittest.TestCase):
    def test_nofollow_metadata_reader_rejects_leaf_and_ancestor_symlinks(self):
        with tempfile.TemporaryDirectory(dir=BASE) as temp:
            root=Path(temp); (root/'real').mkdir(); (root/'real'/'source.py').write_bytes(b'accepted')
            (root/'leaf.py').symlink_to(root/'real'/'source.py')
            (root/'alias').symlink_to(root/'real', target_is_directory=True)
            self.assertEqual(phased.source_bytes(root/'real'/'source.py'), b'accepted')
            for path in (root/'leaf.py',root/'alias'/'source.py'):
                with self.subTest(path=path.name), self.assertRaises(OSError): phased.source_bytes(path)

    def test_existing_cache_change_and_unknown_new_file_fail_but_exact_new_derivative_passes(self):
        with tempfile.TemporaryDirectory(dir=BASE) as temp:
            root=Path(temp); project=root/'projects'/('a'*32); (project/'previews').mkdir(parents=True)
            existing=project/'previews'/(('b'*64)+'.png'); existing.write_bytes(b'old-preview')
            (project/'project.json').write_bytes(b'{"id":"protected"}')
            before=accepted.tree(root)
            (project/'previews'/(('c'*64)+'.png')).write_bytes(b'new-preview')
            result=phased.compare_workspace(accepted,before,accepted.tree(root))
            self.assertTrue(result['passed']);self.assertEqual(result['added_derivative_count'],1)
            existing.write_bytes(b'changed-preview')
            result=phased.compare_workspace(accepted,before,accepted.tree(root))
            self.assertFalse(result['passed']);self.assertEqual(result['changed_count'],1)
            existing.write_bytes(b'old-preview');(project/'unknown.txt').write_bytes(b'not-allowed')
            result=phased.compare_workspace(accepted,before,accepted.tree(root))
            self.assertFalse(result['passed']);self.assertEqual(result['unexpected_added_count'],1)
            self.assertNotIn('unknown.txt',str(result))

    def test_names_only_inspects_types_and_refuses_symlink_and_environment_files(self):
        with tempfile.TemporaryDirectory(dir=BASE) as temp:
            root=Path(temp);(root/'projects').mkdir();(root/'projects'/'file').write_bytes(b'data')
            self.assertEqual(phased.names_only(accepted,root),['projects/file'])
            (root/'alias').symlink_to(root/'projects',target_is_directory=True)
            with self.assertRaises(ValueError):phased.names_only(accepted,root)
            (root/'alias').unlink();(root/'.env').write_bytes(b'not-read')
            with self.assertRaises(ValueError):phased.names_only(accepted,root)

    def test_phase_validation_refuses_missing_guard_rebound_source_failure_force_and_unsupported_tool(self):
        binding={'test_only':'guard-unit-fixture-not-native-evidence'}
        report={'schema':phased.SCHEMA+':tool','tool':'ray-optics','binding':binding,'passed':True,
                'checks':{name:True for name in phased.TOOL_CHECKS},'force_termination_used':False,
                'permissions_requested':False,'production_code_injected':False,
                'ordinary_quit':{'passed':True,'owned_app_terminated':True,'controller_exit_code':0,
                                 'operation':'terminate','termination_mechanism':'NSRunningApplication.terminate','force_termination_used':False},
                'canonical_quit_receipt':{'durable_jobs_at_shutdown_count':0},
                'installed_tool_readiness':{'available':True},'preservation_status':'pending_separate_verify_phase'}
        phased.validate_phase(accepted,report,'ray-optics',binding)
        variations=[]
        item=copy.deepcopy(report);item['checks'].pop('workspace_ownership_released');item['checks']['unrelated']=True;variations.append(item)
        item=copy.deepcopy(report);item['binding']={'wrong':'source'};variations.append(item)
        item=copy.deepcopy(report);item['passed']=False;variations.append(item)
        item=copy.deepcopy(report);item['ordinary_quit']['force_termination_used']=True;variations.append(item)
        item=copy.deepcopy(report);item['error']='preserved failed observation';variations.append(item)
        for item in variations:
            with self.subTest(variation=item),self.assertRaises(ValueError):phased.validate_phase(accepted,item,'ray-optics',binding)
        item=copy.deepcopy(report);item['tool']='unconfigured-provider'
        with self.assertRaises(ValueError):phased.validate_phase(accepted,item,'unconfigured-provider',binding)
        for tool in ('deep','retime'):
            item=copy.deepcopy(report);item['tool']=tool
            if tool=='retime':
                with self.assertRaises(ValueError):phased.validate_phase(accepted,item,tool,binding)
                item['installed_tool_readiness']['retime_probe']=self.retime_guard_fixture()
            phased.validate_phase(accepted,item,tool,binding)

    @staticmethod
    def retime_guard_fixture():
        # Explicit synthetic input to a pure validator, never a native report.
        return {'available':True,'versions':{'numpy':'2.3.5','opencv-python-headless':'4.11.0.86'},
                'method':'OpenCV DIS medium bidirectional dense optical flow',
                'operation_probe':{'median_displacement_error_pixels':.1},
                'analysis_edge':640,'max_frames':240,'max_edge':1280,'max_pixels':1280*720,
                'rendered_playback':True}

    def test_retime_requires_pinned_actual_probe_fields_and_finite_numeric_tolerance(self):
        value=self.retime_guard_fixture()
        self.assertEqual(phased.validate_retime_readiness(value)['operation_probe'],value['operation_probe'])
        variants=[]
        for error in (True,None,'0.1',float('nan'),float('inf'),-.01,.201):
            v=copy.deepcopy(value);v['operation_probe']['median_displacement_error_pixels']=error;variants.append(v)
        for key in ('operation_probe','versions','method','rendered_playback','max_frames'):
            v=copy.deepcopy(value);v.pop(key);variants.append(v)
        v=copy.deepcopy(value);v['versions']['numpy']='2.3.6';variants.append(v)
        v=copy.deepcopy(value);v['available']=1;variants.append(v)
        v=copy.deepcopy(value);v['max_frames']=True;variants.append(v)
        for i,v in enumerate(variants):
            with self.subTest(variant=i),self.assertRaises(ValueError):phased.validate_retime_readiness(v)

    def test_core_requires_exact_accepted_commit_and_actual_git_tree(self):
        self.assertEqual(phased.validate_core_commit(phased.CORE),phased.CORE)
        for value in (None,'pending','HEAD','0'*40,'530ba2400571a8b67efa2d9ab28997f65920c006'):
            with self.subTest(value=value),self.assertRaises(ValueError):phased.validate_core_commit(value)
        phased.assert_core_tree(accepted,BASE.parents[4],phased.CORE)
        with tempfile.TemporaryDirectory(dir=BASE) as temp:
            subprocess.run(['git','init','--quiet',temp],check=True,capture_output=True)
            with self.assertRaises(ValueError):phased.assert_core_tree(accepted,Path(temp),phased.CORE)

if __name__=='__main__':unittest.main(verbosity=2)
