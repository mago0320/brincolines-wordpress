"""Exercise production-domain isolation with fake WP-CLI and real PHP."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
DOMAIN = 'brincolinesjumping.com'
PHP_IMAGE = 'wordpress@sha256:1e6215749283955d5c9ffea6c297651ed23cdfdbb91677ad7abd705b2682f2cf'

FAKE_WP = r'''
import json, os, pathlib, subprocess, sys
root = pathlib.Path(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--path=')))
fixture = json.loads((root / '.fixture.json').read_text())
with open(os.environ['BJ_TEST_CALLS'], 'a') as calls:
    calls.write(json.dumps({'root': str(root), 'args': sys.argv[1:]}) + '\n')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
if args[:3] == ['option', 'get', 'home']:
    print(fixture['home'])
elif args[:3] == ['config', 'is-true', 'MULTISITE']:
    sys.exit(0 if fixture.get('multisite') else 1)
elif args[0] == 'eval':
    # Bootstrap a small WP API fixture, then execute the actual inventory PHP.
    prelude = r"""
    $f = json_decode(getenv('BJ_TEST_FIXTURE'), true);
    define('ABSPATH', getenv('BJ_TEST_ROOT') . '/');
    define('WP_CONTENT_DIR', ABSPATH . 'wp-content');
    function get_option($key) { global $f; return $f['options'][$key] ?? ''; }
    function is_multisite() { global $f; return $f['multisite'] ?? false; }
    function wp_get_themes() { return array(); }
    function get_plugins() { return array('sample/main.php' => array('Name' => 'Fixture', 'Version' => '1.0')); }
    function is_plugin_active($file) { return true; }
    function get_theme_root() { return WP_CONTENT_DIR . '/themes'; }
    function get_bloginfo($key) { return '6.8.3'; }
    function wp_json_encode($value, $flags) { return json_encode($value, $flags); }
    """
    env = dict(os.environ, BJ_TEST_ROOT=str(root), BJ_TEST_FIXTURE=json.dumps(fixture))
    result = subprocess.run(['php', '-r', prelude + args[1]], env=env)
    sys.exit(result.returncode)
else:
    raise SystemExit('Unexpected WP-CLI command')
'''


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = tempfile.TemporaryDirectory(prefix='brincos-php-runtime-')
        cls.container = None
        cls.native_php = shutil.which('php')
        cls.runtime_bin = Path(cls.runtime.name)
        if not cls.native_php:
            # Only a local PHP process; no web server, database or host ports.
            cls.container = subprocess.check_output([
                'docker', 'run', '-d', '--mount',
                'type=bind,source=' + cls.runtime.name + ',target=' + cls.runtime.name + ',readonly',
                '--entrypoint', 'sleep', PHP_IMAGE, '600'
            ], text=True).strip()
            php = cls.runtime_bin / 'php'
            names = ('BJ_TEST_FIXTURE', 'BJ_TEST_ROOT', 'BJ_AUDIT_DOMAIN', 'BJ_AUDIT_HOME', 'BJ_AUDIT_ROOT', 'BJ_AUDIT_USER', 'BJ_AUDIT_HOST')
            options = ' '.join('-e ' + name for name in names)
            php.write_text('#!/bin/sh\nexec docker exec -i ' + options + ' ' + shlex.quote(cls.container) + ' php "$@"\n')
            php.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        if cls.container:
            subprocess.run(['docker', 'rm', '-f', cls.container], check=True, stdout=subprocess.DEVNULL)
        cls.runtime.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='brincos-discovery-test-', dir=self.runtime.name)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'account'
        self.home.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        (self.bin / 'wp').write_text('#!' + sys.executable + '\n' + FAKE_WP)
        (self.bin / 'wp').chmod(0o700)
        self.calls = self.base / 'calls.jsonl'
        self.env = dict(os.environ, HOME=str(self.home), BJ_TEST_CALLS=str(self.calls))
        self.env['PATH'] = str(self.bin) + ':' + str(self.runtime_bin) + ':' + os.environ['PATH']

    def wordpress(self, relative, domain=DOMAIN, **extra):
        root = self.home / relative
        for directory in ('wp-includes', 'wp-content/themes', 'wp-admin/includes'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for file in ('wp-load.php', 'wp-settings.php', 'wp-admin/includes/plugin.php'):
            (root / file).write_text('<?php\n')
        url = 'https://' + domain
        fixture = {'home': url, 'options': {'home': url, 'siteurl': url, 'template': 'kadence', 'stylesheet': 'kadence', 'page_on_front': 42, 'show_on_front': 'page'}, **extra}
        (root / '.fixture.json').write_text(json.dumps(fixture))
        return root

    def run_discovery(self, hint='', target=DOMAIN):
        return subprocess.run(['bash', str(REPO / 'scripts/discover-wordpress.sh'), target, str(hint)], env=self.env, capture_output=True, text=True, timeout=50)

    def assert_failure(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, '')

    def logged_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_exact_hint_returns_scoped_inventory(self):
        root = self.wordpress('public_html')
        result = self.run_discovery(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['wordpress_root'], str(root))
        self.assertEqual(report['target_domain'], DOMAIN)
        self.assertEqual(report['active_stylesheet'], 'kadence')
        self.assertTrue(report['match_verified'])
        self.assertEqual(len(report['plugins']), 1)
        self.assertNotIn('password', result.stdout.lower())

    def test_foreign_hint_is_rejected_without_inventory(self):
        root = self.wordpress('foreign', 'otro-dominio.example')
        self.assert_failure(self.run_discovery(root), 'no corresponde')
        self.assertFalse(any('eval' in call['args'] for call in self.logged_calls()))

    def test_home_search_inventories_only_target(self):
        self.wordpress('public_html/another', 'otro-dominio.example')
        target = self.wordpress('custom/target site')
        result = self.run_discovery()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['wordpress_root'], str(target))
        evals = [call for call in self.logged_calls() if 'eval' in call['args']]
        self.assertEqual([call['root'] for call in evals], [str(target)])

    def test_two_matches_are_rejected(self):
        self.wordpress('public_html')
        self.wordpress('copied-site')
        self.assert_failure(self.run_discovery(), '2 instalaciones')
        self.assertFalse(any('eval' in call['args'] for call in self.logged_calls()))

    def test_no_match_is_rejected(self):
        self.wordpress('public_html', 'otro-dominio.example')
        self.assert_failure(self.run_discovery(), '0 instalaciones')

    def test_www_canonical_domain_is_allowed(self):
        root = self.wordpress('site', 'www.' + DOMAIN)
        result = self.run_discovery(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['home_url'], 'https://www.' + DOMAIN)

    def test_deceptive_domain_is_rejected(self):
        root = self.wordpress('site', DOMAIN + '.evil.example')
        self.assert_failure(self.run_discovery(root), 'no corresponde')

    def test_multisite_is_rejected(self):
        root = self.wordpress('site', multisite=True)
        self.assert_failure(self.run_discovery(root), 'multisite')

    def test_outside_home_root_is_rejected(self):
        self.assert_failure(self.run_discovery('/tmp'), 'no corresponde')
        self.assertEqual(self.logged_calls(), [])

    def test_different_target_is_rejected_before_search(self):
        self.wordpress('public_html')
        self.assert_failure(self.run_discovery(target='otro-dominio.example'), 'fuera del alcance')
        self.assertEqual(self.logged_calls(), [])

    def test_cpanel_exact_domain_root_avoids_other_sites(self):
        root = self.wordpress('custom/target')
        self.wordpress('public_html/other', 'otro-dominio.example')
        uapi = self.bin / 'uapi'
        response = {'result': {'data': {'documentroot': str(root)}}}
        uapi.write_text('#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(json.dumps(response)) + '\n')
        uapi.chmod(0o700)
        result = self.run_discovery()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(call['root'] == str(root) for call in self.logged_calls()))

    def test_domain_is_rechecked_before_inventory(self):
        root = self.wordpress('site')
        fixture_path = root / '.fixture.json'
        fixture = json.loads(fixture_path.read_text())
        fixture['options']['home'] = 'https://otro-dominio.example'
        fixture_path.write_text(json.dumps(fixture))
        self.assert_failure(self.run_discovery(root), 'El dominio cambió')

    def test_relative_hint_is_rejected(self):
        self.assert_failure(self.run_discovery('public_html'), 'debe ser absoluta')


if __name__ == '__main__':
    unittest.main()
