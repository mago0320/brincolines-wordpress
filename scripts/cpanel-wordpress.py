#!/usr/bin/env python3
"""Read-only inventory through cPanel Terminal, limited to the verified site."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import ssl
import sys
import time
import urllib.error
import uuid

spec = importlib.util.spec_from_file_location('cpanel_discover', Path(__file__).with_name('cpanel-discover.py'))
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def remote_script(root, marker):
    # No plugin/theme bootstrap, database writes, or account-wide commands.
    return '''set -eu
wp_site_path=ROOT
if ! command -v wp >/dev/null 2>&1; then
 printf 'MARKER_BEGIN{"wp_cli_available":false}MARKER_END\\n'
 exit 0
fi
wp_site_home=$(wp --path="$wp_site_path" --skip-plugins --skip-themes option get home)
case "$wp_site_home" in
 https://brincolinesjumping.com|https://brincolinesjumping.com/|https://www.brincolinesjumping.com|https://www.brincolinesjumping.com/|http://brincolinesjumping.com|http://brincolinesjumping.com/|http://www.brincolinesjumping.com|http://www.brincolinesjumping.com/) ;;
 *) printf 'MARKER_BEGIN{"domain_guard_passed":false}MARKER_END\\n'; exit 0 ;;
esac
printf 'MARKER_BEGIN'
wp --path="$wp_site_path" --skip-plugins --skip-themes eval 'echo wp_json_encode(array("wp_cli_available"=>true,"home"=>get_option("home"),"siteurl"=>get_option("siteurl"),"active_template"=>get_option("template"),"active_stylesheet"=>get_option("stylesheet"),"active_plugins"=>get_option("active_plugins"),"front_page_id"=>get_option("page_on_front"),"front_page_mode"=>get_option("show_on_front"),"is_multisite"=>is_multisite(),"elementor_data_present"=>(bool)get_post_meta(get_option("page_on_front"),"_elementor_data",true)));'
printf 'MARKER_END\\n'
'''.replace('ROOT', shlex.quote(root), 1).replace('MARKER', marker)


def validate_inventory(data):
    if not isinstance(data, dict) or data.get('wp_cli_available') is not True:
        raise panel.PanelError('wp_cli_not_verified')
    for field in ('home', 'siteurl'):
        value = data.get(field)
        if not isinstance(value, str) or value.rstrip('/') not in {
            scheme + host for scheme in ('http://', 'https://')
            for host in (panel.DOMAIN, 'www.' + panel.DOMAIN)
        }:
            raise panel.PanelError('wordpress_domain_out_of_scope')
    if data.get('is_multisite') is not False:
        raise panel.PanelError('multisite_or_unknown_scope')
    fields = {'wp_cli_available', 'home', 'siteurl', 'active_template', 'active_stylesheet',
              'active_plugins', 'front_page_id', 'front_page_mode', 'is_multisite', 'elementor_data_present'}
    return {key: value for key, value in data.items() if key in fields}


def terminal_inventory(session, root, connector=None):
    if connector is None:
        from websockets.sync.client import connect
        connector = connect
    marker = 'BRINCOS_' + uuid.uuid4().hex
    uri = session.base.replace('https://', 'wss://', 1) + session.session + '/websocket/Shell?rows=24&cols=120'
    with connector(uri, ssl=ssl.create_default_context(), origin=session.base,
                   additional_headers={'Cookie': session.cookie}, open_timeout=20,
                   close_timeout=3, max_size=1_000_000) as socket:
        try:
            socket.recv(timeout=3)
        except TimeoutError:
            pass
        socket.send('stty -echo; unset HISTFILE; set +o history\n')
        try:
            socket.recv(timeout=2)
        except TimeoutError:
            pass
        socket.send('bash -c ' + shlex.quote(remote_script(root, marker)) + '\n')
        collected = ''
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                chunk = socket.recv(timeout=min(10, remaining))
            except TimeoutError:
                continue
            collected += chunk.decode(errors='replace') if isinstance(chunk, bytes) else chunk
            if len(collected) > 2_000_000:
                raise panel.PanelError('terminal_output_limit')
            match = re.search(re.escape(marker) + '_BEGIN(.*?)' + re.escape(marker) + '_END', collected, re.S)
            if match:
                result = validate_inventory(json.loads(match.group(1)))
                socket.send('exit\n')
                return result
        raise panel.PanelError('terminal_inventory_timeout')


def discover(user, password, session_factory=None, inventory_reader=None):
    report = {'target_domain': panel.DOMAIN, 'authenticated': False, 'administrative_access_verified': False}
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user) or not password:
        return dict(report, status='requires_cpanel_credentials')
    try:
        session = (session_factory or panel.PanelSession)(user, password)
        root = panel.validate_domain(session.api_call('DomainInfo', 'single_domain_data', {'domain': panel.DOMAIN}))
        files = session.api_call('Fileman', 'list_files', {'dir': root})
        if not isinstance(files, list):
            raise panel.PanelError('unexpected_directory_listing')
        names = {str(item.get('file', item.get('name', ''))) for item in files if isinstance(item, dict)}
        if not {'wp-load.php', 'wp-settings.php', 'wp-includes', 'wp-content'}.issubset(names):
            raise panel.PanelError('wordpress_files_not_verified')
        report.update(authenticated=True, tls_verified=True, wordpress_files_verified=True)
        result = (inventory_reader or terminal_inventory)(session, root)
        report.update(validate_inventory(result), administrative_access_verified=True,
                      status='wordpress_inventory_verified', transport='cpanel_https_terminal')
    except urllib.error.HTTPError as error:
        report.update(status='http_error', http_status=error.code)
    except panel.PanelError as error:
        report.update(status='administrative_access_blocked', reason=str(error))
    except Exception as error:
        # Transport errors can embed session URLs; return only their type.
        report.update(status='administrative_access_failed', error_type=type(error).__name__)
    return report


def main():
    user = os.environ.get('BH_USER', '')
    password = os.environ.get('BH_CPANEL_PASSWORD', '')
    if '--interactive' in sys.argv:
        user = getpass.getpass('Usuario cPanel (entrada oculta): ')
        password = getpass.getpass('Contraseña cPanel (entrada oculta): ')
    report = discover(user, password)
    output = Path('.local/audit')
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    target = output / 'cpanel-wordpress.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    target.chmod(0o600)
    print(json.dumps(report, separators=(',', ':')))
    return 0 if report.get('administrative_access_verified') else 2


if __name__ == '__main__':
    raise SystemExit(main())
