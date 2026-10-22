"""Portable guard tests only; these do not simulate/claim any Mac acceptance."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

BASE = Path('/workspace/scratch/091f394ee5df')

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

phased = module('phased_guards', BASE / 'run_installed_readiness_phased.py')
accepted = module('accepted_guards', BASE / 'cinematicum-next/scripts/studio/verification/0.11.0/tools/installed-launch-01/run_installed_launch.py')

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

    def test_phase_validation_refuses_missing_guard_rebound_source_failure_force_and_deep(self):
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
        item=copy.deepcopy(report);item['tool']='deep'
        with self.assertRaises(ValueError):phased.validate_phase(accepted,item,'deep',binding)

if __name__=='__main__':unittest.main(verbosity=2)
