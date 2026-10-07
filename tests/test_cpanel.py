import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('cpanel_discover', Path(__file__).resolve().parents[1] / 'scripts/cpanel-discover.py')
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class PanelTests(unittest.TestCase):
    def test_foreign_domain_is_rejected_before_file_access(self):
        with patch.object(panel, 'api_call', return_value={'domain':'other.example','documentroot':'/home/user/other'}) as call:
            report = panel.discover('user', 'secret-must-not-be-returned')
        self.assertEqual(report['reason'], 'returned_domain_out_of_scope')
        self.assertEqual(call.call_count, 1)
        self.assertNotIn('secret-must-not-be-returned', json.dumps(report))

    def test_parent_traversal_and_root_are_rejected(self):
        for root in ['/', '/home/user/../other', '/home/user/\nwrong']:
            with self.subTest(root=root), self.assertRaises(panel.PanelError):
                panel.validate_domain({'domain':panel.DOMAIN,'documentroot':root})

    def test_scoped_wordpress_files_are_identified_without_reading_configuration(self):
        root='/home/user/public_html'
        with patch.object(panel, 'api_call', side_effect=[{'domain':panel.DOMAIN,'documentroot':root}, [{'file':name} for name in ['wp-load.php','wp-settings.php','wp-includes','wp-content']]]) as call:
            report = panel.discover('user', 'secret-must-not-be-returned')
        self.assertEqual(report['wordpress_root_candidate'], root)
        self.assertEqual(call.call_args.args[2:5], ('Fileman','list_files',{'dir':root}))
        self.assertNotIn('secret-must-not-be-returned', json.dumps(report))

    def test_missing_token_checks_only_https_with_verification(self):
        response=MagicMock()
        response.__enter__.return_value.status=401
        with patch.object(panel, 'secure_open', return_value=response) as request:
            report=panel.discover('user','')
        self.assertTrue(report['tls_verified'])
        self.assertFalse(report['authenticated'])
        self.assertEqual(report['status'],'requires_cpanel_authentication')
        self.assertFalse(request.call_args.args[0].has_header('Authorization'))
    def test_tls_checks_are_preserved_in_secure_opener(self):
        with patch.object(panel.urllib.request, 'build_opener') as opener, patch.object(panel.urllib.request, 'HTTPSHandler', wraps=panel.urllib.request.HTTPSHandler) as https:
            panel.secure_open(panel.urllib.request.Request('https://' + panel.HOST + ':2083/'))
        context=https.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, panel.ssl.CERT_REQUIRED)

    def test_credentials_never_follow_redirects(self):
        request=panel.urllib.request.Request('https://' + panel.HOST + ':2083/',headers={'Authorization':'private-fixture'})
        self.assertIsNone(panel.NoRedirect().redirect_request(request,None,302,'',{},'https://other.example/'))

    def test_password_authentication_stays_private_and_domain_scoped(self):
        with patch.object(panel, 'api_call', side_effect=[{'domain':panel.DOMAIN,'documentroot':'/home/user/site'}, []]) as call:
            report=panel.discover('user','','password-must-not-be-returned')
        self.assertTrue(report['authenticated'])
        self.assertNotIn('password-must-not-be-returned',json.dumps(report))
        self.assertTrue(call.call_args.kwargs['password_auth'])

    def test_public_reports_hide_account_names_in_paths(self):
        report={'documentroot':'/home/private-account/site','wordpress_root_candidate':'/home/private-account/site','authenticated':True}
        with patch.dict(panel.os.environ, {'GITHUB_ACTIONS':'true'}), patch.object(panel,'discover',return_value=report), patch.object(panel,'Path') as path, patch('builtins.print') as output:
            panel.main()
        written=path.return_value.__truediv__.return_value.write_text.call_args.args[0]
        self.assertNotIn('private-account',written)
        self.assertNotIn('private-account',output.call_args.args[0])
        self.assertIn('[private]',written)

    def test_arbitrary_cpanel_operations_are_rejected(self):
        with self.assertRaises(panel.PanelError):
            panel.endpoint('Fileman','save_file_content',{})


if __name__ == '__main__':
    unittest.main()
