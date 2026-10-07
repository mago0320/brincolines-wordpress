import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

spec=importlib.util.spec_from_file_location('cpanel_wordpress',Path(__file__).resolve().parents[1]/'scripts/cpanel-wordpress.py')
wp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(wp)


def inventory():
    return {'wp_cli_available':True,'home':'https://brincolinesjumping.com',
            'siteurl':'https://brincolinesjumping.com','is_multisite':False,
            'active_template':'kadence','active_stylesheet':'kadence',
            'active_plugins':[],'front_page_id':'42','elementor_data_present':True}


def scoped_session():
    session=MagicMock()
    session.api_call.side_effect=[{'domain':wp.panel.DOMAIN,'documentroot':'/home/private-account/public_html'},
                                [{'file':name} for name in ['wp-load.php','wp-settings.php','wp-includes','wp-content']]]
    return session


class WordPressPanelTests(unittest.TestCase):
    def test_foreign_documentroot_stops_before_terminal(self):
        session=MagicMock()
        session.api_call.return_value={'domain':'other.example','documentroot':'/home/user/other'}
        reader=MagicMock()
        report=wp.discover('user','private-password',session_factory=lambda *args:session,inventory_reader=reader)
        reader.assert_not_called()
        self.assertEqual(report['reason'],'returned_domain_out_of_scope')
        self.assertFalse(report['administrative_access_verified'])

    def test_missing_wordpress_files_stops_before_terminal(self):
        session=scoped_session()
        session.api_call.side_effect=[{'domain':wp.panel.DOMAIN,'documentroot':'/home/user/site'},[]]
        reader=MagicMock()
        report=wp.discover('user','private-password',session_factory=lambda *args:session,inventory_reader=reader)
        reader.assert_not_called()
        self.assertEqual(report['reason'],'wordpress_files_not_verified')

    def test_foreign_wordpress_url_and_multisite_are_rejected(self):
        for field,value in [('home','https://other.example'),('siteurl','https://other.example'),('is_multisite',True),('is_multisite',None)]:
            with self.subTest(field=field):
                data=inventory();data[field]=value
                with self.assertRaises(wp.panel.PanelError):wp.validate_inventory(data)

    def test_verified_report_contains_no_account_paths_or_credentials(self):
        session=scoped_session()
        reader=MagicMock(return_value=dict(inventory(),password='reflected-password',documentroot='/home/private-account/public_html'))
        report=wp.discover('user','private-password',session_factory=lambda *args:session,inventory_reader=reader)
        self.assertTrue(report['administrative_access_verified'])
        self.assertEqual(report['active_stylesheet'],'kadence')
        rendered=json.dumps(report)
        for secret in ['private-password','reflected-password','private-account']:self.assertNotIn(secret,rendered)
        reader.assert_called_once_with(session,'/home/private-account/public_html')

    def test_transport_exceptions_cannot_leak_session_urls(self):
        report=wp.discover('user','private-password',session_factory=lambda *args:scoped_session(),
                           inventory_reader=MagicMock(side_effect=RuntimeError('https://host/cpsess123/private-password')))
        self.assertEqual(report['error_type'],'RuntimeError')
        self.assertNotIn('cpsess123',json.dumps(report))
        self.assertNotIn('private-password',json.dumps(report))

    def test_missing_credentials_do_not_attempt_login(self):
        login=MagicMock()
        report=wp.discover('user','',session_factory=login)
        login.assert_not_called()
        self.assertEqual(report['status'],'requires_cpanel_credentials')

    def test_pasted_terminal_newline_is_removed_without_changing_password(self):
        login=MagicMock(return_value=scoped_session())
        report=wp.discover('user','private-password\r\n',session_factory=login,inventory_reader=lambda *args:inventory())
        login.assert_called_once_with('user','private-password')
        self.assertTrue(report['password_terminal_linebreak_removed'])
        self.assertTrue(report['administrative_access_verified'])
        self.assertNotIn('private-password',json.dumps(report))

    def test_embedded_linebreak_stops_before_authentication(self):
        login=MagicMock()
        report=wp.discover('user','private\npassword',session_factory=login)
        login.assert_not_called()
        self.assertEqual(report['reason'],'password_contains_embedded_linebreak')

    def test_spaces_in_password_are_preserved(self):
        login=MagicMock(return_value=scoped_session())
        report=wp.discover('user',' private-password ',session_factory=login,inventory_reader=lambda *args:inventory())
        login.assert_called_once_with('user',' private-password ')
        self.assertTrue(report['administrative_access_verified'])

    def test_http_failure_identifies_stage_without_leaking_response(self):
        session=scoped_session()
        session.api_call.side_effect=wp.urllib.error.HTTPError('https://host/cpsess-private',401,'private-password',{},None)
        report=wp.discover('user','private-password',session_factory=lambda *args:session)
        self.assertEqual(report['stage'],'domain_lookup')
        self.assertTrue(report['authenticated'])
        self.assertEqual(report['http_status'],401)
        self.assertNotIn('private-password',json.dumps(report))
        self.assertNotIn('cpsess-private',json.dumps(report))

    def test_terminal_verifies_tls_and_keeps_cookie_on_official_endpoint(self):
        session=MagicMock(base='https://'+wp.panel.HOST+':2083',session='/cpsess123',cookie='cpsession=private-cookie')
        socket=MagicMock()
        socket.recv.side_effect=[b'greeting',b'prompt',('BRINCOS_nonce_BEGIN'+json.dumps(inventory())+'BRINCOS_nonce_END').encode()]
        connector=MagicMock()
        connector.return_value.__enter__.return_value=socket
        with patch.object(wp.uuid,'uuid4',return_value=MagicMock(hex='nonce')):
            result=wp.terminal_inventory(session,'/home/user/site',connector=connector)
        self.assertEqual(result['active_stylesheet'],'kadence')
        self.assertEqual(connector.call_args.args[0],'wss://'+wp.panel.HOST+':2083/cpsess123/websocket/Shell?rows=24&cols=120')
        context=connector.call_args.kwargs['ssl']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,wp.ssl.CERT_REQUIRED)
        self.assertEqual(connector.call_args.kwargs['additional_headers'],{'Cookie':'cpsession=private-cookie'})
        self.assertEqual(socket.send.call_args.args[0],'exit\n')


if __name__=='__main__':unittest.main()
