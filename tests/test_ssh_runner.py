"""Verify fail-closed SSH trust and safe runner options without production."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class SSHRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='brincos-ssh-runner-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        shutil.copytree(REPO / 'scripts', self.repo / 'scripts')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.called = self.base / 'authenticated'
        self.arguments = self.base / 'ssh-args.json'
        self.env = dict(os.environ, BH_HOST='example.test', BH_USER='testuser',
                        BH_PORT='22', BH_KEY='private-material-must-never-be-printed',
                        BH_KNOWN_HOSTS='', BH_FINGERPRINT='', BH_ROOT_HINT='',
                        RUNNER_TEMP=str(self.base))
        self.env['PATH'] = str(self.bin) + ':' + os.environ['PATH']
        # Use a fresh synthetic public host key, never a user's credentials.
        key = self.base / 'hostkey'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        self.host_line = 'example.test ' + key.with_suffix('.pub').read_text().strip()
        keyfile = self.base / 'scanned'
        keyfile.write_text(self.host_line + '\n')
        self.fingerprint = subprocess.check_output(['ssh-keygen', '-lf', str(keyfile)], text=True).split()[1]
        scan = self.bin / 'ssh-keyscan'
        scan.write_text('#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(self.host_line) + '\n')
        scan.chmod(0o700)
        add = self.bin / 'ssh-add'
        add.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(self.called)) + '\n')
        add.chmod(0o700)
        ssh = self.bin / 'ssh'
        report = {'target_domain': 'brincolinesjumping.com', 'match_verified': True,
                  'wordpress_version': '6.8.3', 'active_stylesheet': 'kadence', 'plugins': []}
        ssh.write_text('#!/usr/bin/env python3\nimport json, pathlib, sys\n'
                       + 'pathlib.Path(' + repr(str(self.arguments)) + ').write_text(json.dumps(sys.argv[1:]))\n'
                       + 'print(' + repr(json.dumps(report)) + ')\n')
        ssh.chmod(0o700)

    def run_runner(self):
        result = subprocess.run(['bash', str(self.repo / 'scripts/ssh-discover.sh')], env=self.env,
                                capture_output=True, text=True, timeout=30)
        self.assertNotIn(self.env['BH_KEY'], result.stdout + result.stderr)
        self.assertEqual(list(self.base.glob('brincos-ssh.*')), [], 'Key temporary directory must be removed')
        return result

    def test_missing_credential_reports_only_name(self):
        self.env['BH_USER'] = ''
        result = self.run_runner()
        self.assertEqual(result.returncode, 2)
        self.assertIn('BANAHOST_SSH_USER', result.stderr)
        self.assertFalse(self.called.exists())

    def test_hostname_injection_is_rejected(self):
        self.env['BH_HOST'] = 'example.test; touch /tmp/wrong'
        result = self.run_runner()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.called.exists())

    def test_invalid_port_is_rejected(self):
        self.env['BH_PORT'] = '65536'
        result = self.run_runner()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.called.exists())

    def test_missing_server_trust_stops_before_key_loading(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 3)
        self.assertIn('aún sin verificar', result.stderr)
        self.assertFalse(self.called.exists())
        fingerprints = self.repo / '.local/audit/host-key-fingerprints.txt'
        self.assertIn(self.fingerprint, fingerprints.read_text())

    def test_wrong_fingerprint_stops_before_authentication(self):
        self.env['BH_FINGERPRINT'] = 'SHA256:' + ('A' * 43)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn('NO coincide', result.stderr)
        self.assertFalse(self.called.exists())

    def test_matching_fingerprint_enforces_strict_ssh(self):
        self.env['BH_FINGERPRINT'] = self.fingerprint
        self.env['BH_ROOT_HINT'] = '/home/testuser/a site'
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.arguments.read_text())
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('ForwardAgent=no', args)
        self.assertIn('IdentitiesOnly=yes', args)
        self.assertIn('BatchMode=yes', args)
        self.assertEqual(args[-2], 'testuser@example.test')
        self.assertTrue(self.called.exists())
        report = json.loads((self.repo / '.local/audit/wordpress-inventory.json').read_text())
        self.assertTrue(report['match_verified'])

    def test_known_hosts_of_another_server_is_rejected(self):
        self.env['BH_KNOWN_HOSTS'] = self.host_line.replace('example.test ', 'other.test ', 1)
        result = self.run_runner()
        self.assertEqual(result.returncode, 3)
        self.assertFalse(self.called.exists())

    def test_matching_known_hosts_is_reused(self):
        self.env['BH_KNOWN_HOSTS'] = self.host_line
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.called.exists())


if __name__ == '__main__':
    unittest.main()
