import base64
import json
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from safety_games.archive import UnsafeArchive, check_git_history, contains_secret, create_research_archive, inspect_archive
from safety_games.judge import IndependentScientificJudge, JudgeAssessment, JudgeEvidence, JudgeInput, JudgeVerdict


class ArchiveSafetyTests(unittest.TestCase):
    def test_allowlist_excludes_env_virtualenv_cache_and_unknown_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name,text in {'.env':'GROQ_API_KEY=synthetic-fixture-secret','.env.example':'GROQ_API_KEY=',
                              'README.md':'fixture','.gitignore':'.env\n','private.txt':'private',
                              '.venv/file':'excluded','safety_games/__pycache__/byte.pyc':'excluded',
                              'safety_games/ok.py':'pass','docs/.env.backup':'excluded',
                              'configs/prod.env.local':'excluded','configs/credentials.json':'excluded'}.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
            output=root/'exports'/'research.zip'
            report=create_research_archive(root,output)
            self.assertFalse(report['secret_found'])
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()),{'README.md','.env.example','.gitignore','safety_games/ok.py'})
            with self.assertRaises(FileExistsError):create_research_archive(root,output)

    def test_raw_and_base64_snapshot_credentials_stop_export(self):
        secret=b'synthetic-secret-12345'
        self.assertTrue(contains_secret(b'prefix '+secret,(secret,)))
        raw=json.dumps({'kind':'file','encoding':'base64','content':base64.b64encode(b'prefix '+secret+b' suffix').decode()}).encode()
        self.assertTrue(contains_secret(raw,(secret,)))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'docs').mkdir()
            (root/'.env').write_text('GROQ_API_KEY='+secret.decode(),encoding='utf-8')
            (root/'docs'/'bad.json').write_bytes(raw)
            with self.assertRaises(UnsafeArchive):create_research_archive(root,root/'exports'/'bad.zip')
            self.assertFalse((root/'exports'/'bad.zip').exists())

    def test_secret_scanner_source_is_exported_and_still_content_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'scripts').mkdir()
            (root/'scripts'/'check_git_secrets.py').write_text('print("scanner fixture")',encoding='utf-8')
            archive=root/'exports'/'safe.zip'
            create_research_archive(root,archive)
            with zipfile.ZipFile(archive) as z:
                self.assertIn('scripts/check_git_secrets.py',z.namelist())

    def test_archive_inspection_rejects_traversal_env_and_encoded_secret(self):
        for name,raw in (('../escape',b'x'),('nested/.env',b'x'),('docs/bad.txt',b'gsk_'+b'a'*30)):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)/'bad.zip'
                with zipfile.ZipFile(output,'w') as archive:archive.writestr(name,raw)
                with self.assertRaises(UnsafeArchive):inspect_archive(output)

    def test_inspection_rejects_duplicate_entries_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'bad.zip'
            info=zipfile.ZipInfo('link');info.external_attr=(0o120777<<16)
            with zipfile.ZipFile(output,'w') as archive:archive.writestr(info,'/etc/passwd')
            with self.assertRaises(UnsafeArchive):inspect_archive(output)

    def test_git_absence_is_reported_without_claiming_history_was_scanned(self):
        with tempfile.TemporaryDirectory() as temporary:
            report=check_git_history(Path(temporary))
            self.assertFalse(report['git_repository'])
            self.assertFalse(report['history_checked'])

    @unittest.skipUnless(shutil.which('git'), 'Git required for controlled history fixture')
    def test_git_history_detects_removed_previously_committed_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def git(*args):
                env={**os.environ,'GIT_CONFIG_GLOBAL':os.devnull,'GIT_CONFIG_NOSYSTEM':'1'}
                subprocess.run(['git','-C',str(root),'-c','commit.gpgsign=false',*args],capture_output=True,check=True,timeout=30,env=env)
            git('init','-q')
            (root/'.env').write_text('FIXTURE=not-a-real-credential',encoding='utf-8')
            git('add','.env')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','controlled fixture')
            git('rm','-q','.env')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','remove fixture')
            report=check_git_history(root)
            self.assertFalse(report['env_tracked'])
            self.assertTrue(report['env_in_history'])


class JudgeContractTests(unittest.TestCase):
    def test_no_default_judge_or_automatic_api_connection(self):
        with self.assertRaises(TypeError):IndependentScientificJudge()

    def test_verdict_requires_observable_evidence_and_provenance(self):
        kwargs=dict(verdict='uncertain',explanation='insufficient observations',judge_id='fixture',model_version='fixture',
                    input_sha256='a'*64,prompt_sha256='b'*64)
        with self.assertRaises(ValueError):JudgeAssessment(evidence=(),**kwargs)
        evidence=JudgeEvidence('trajectory.jsonl','observed fixture',event_id=1,explanation='observable limitation')
        assessment=JudgeAssessment(evidence=(evidence,),**kwargs)
        self.assertEqual(assessment.to_dict()['verdict'],'uncertain')
        with self.assertRaises(ValueError):JudgeAssessment(evidence=(evidence,),**kwargs,audit_status='human_confirmed')

    def test_scientific_judge_cannot_be_repurposed_as_sanction_component(self):
        with self.assertRaises(ValueError):
            JudgeInput('e','t','problem','initial','final',(),(),{}, {}, {'source':'a'*64},'limited',purpose='assign_penalty')


if __name__=='__main__':unittest.main()
