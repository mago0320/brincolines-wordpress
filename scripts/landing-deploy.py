#!/usr/bin/env python3
"""Manual deployment through the verified cPanel Terminal. No SSH port probing."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import ssl
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


panel = module('panel', 'cpanel-discover.py')
inventory = module('inventory', 'cpanel-wordpress.py')
builder = module('builder', 'build-landing.py')


def terminal_operation(session, root, payload, connector=None):
    if connector is None:
        from websockets.sync.client import connect
        connector = connect
    payload = dict(payload, verified_root=root)
    script = (ROOT / 'scripts/landing-operation.php').read_bytes()
    bundle = json.dumps({'payload': payload, 'script': base64.b64encode(script).decode()}, ensure_ascii=False).encode()
    compressed = gzip.compress(bundle, mtime=0)
    encoded = base64.b64encode(compressed).decode()
    marker = 'BJ_' + uuid.uuid4().hex
    # A wrapped heredoc avoids shell/PTY argument limits; all content is data.
    lines = '\n'.join(encoded[index:index+76] for index in range(0, len(encoded), 76))
    bootstrap = '''$j=json_decode(file_get_contents($argv[1]),true,512,JSON_THROW_ON_ERROR);file_put_contents($argv[2],json_encode($j["payload"],JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES));file_put_contents($argv[3],base64_decode($j["script"],true));chmod($argv[2],0600);chmod($argv[3],0600);'''
    command = '''set -eu
umask 077
wp_site_path=ROOT
wp_site_home=$(wp --path="$wp_site_path" --skip-plugins --skip-themes option get home)
case "$wp_site_home" in https://brincolinesjumping.com|https://brincolinesjumping.com/|https://www.brincolinesjumping.com|https://www.brincolinesjumping.com/) ;; *) exit 3 ;; esac
bj_stage_base="$HOME/.brincolinesjumping-staging"
test ! -L "$bj_stage_base"
mkdir -p "$bj_stage_base"
test "$(readlink -f "$bj_stage_base")" = "$(readlink -f "$HOME")/.brincolinesjumping-staging"
chmod 700 "$bj_stage_base"
bj_stage_dir=$(mktemp -d "$bj_stage_base/release-XXXXXXXX")
base64 -d <<'BUNDLE_END' | gzip -d > "$bj_stage_dir/bundle.json"
ENCODED
BUNDLE_END
php -r BOOTSTRAP "$bj_stage_dir/bundle.json" "$bj_stage_dir/payload.json" "$bj_stage_dir/operation.php"
php -l "$bj_stage_dir/operation.php" >/dev/null
printf 'MARKER_BEGIN'
BJ_PAYLOAD_PATH="$bj_stage_dir/payload.json" wp --path="$wp_site_path" --skip-plugins --skip-themes eval-file "$bj_stage_dir/operation.php"
printf 'MARKER_END\\n'
'''.replace('ROOT', shlex.quote(root), 1).replace('BOOTSTRAP', shlex.quote(bootstrap), 1).replace('ENCODED', lines, 1).replace('MARKER', marker)
    uri = session.base.replace('https://', 'wss://', 1) + session.session + '/websocket/Shell?rows=24&cols=120'
    with connector(uri, ssl=ssl.create_default_context(), origin=session.base, additional_headers={'Cookie': session.cookie}, open_timeout=20, close_timeout=3, max_size=8_000_000) as socket:
        try:
            socket.recv(timeout=2)
        except TimeoutError:
            pass
        socket.send('stty -echo; unset HISTFILE; set +o history\n')
        try:
            socket.recv(timeout=1)
        except TimeoutError:
            pass
        socket.send('bash <<\'' + marker + '_SCRIPT\'\n')
        # Send independently wrapped chunks; no secret values are included.
        for offset in range(0, len(command), 8192):
            socket.send(command[offset:offset+8192])
        socket.send('\n' + marker + '_SCRIPT\n')
        data = ''
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            try:
                chunk = socket.recv(timeout=min(10, deadline-time.monotonic()))
            except TimeoutError:
                continue
            data += chunk.decode(errors='replace') if isinstance(chunk, bytes) else chunk
            if len(data) > 8_000_000:
                raise panel.PanelError('terminal_output_limit')
            match = re.search(re.escape(marker) + '_BEGIN(.*?)' + re.escape(marker) + '_END', data, re.S)
            if match:
                result = json.loads(match.group(1))
                socket.send('exit\n')
                if result.get('ok') is not True:
                    raise panel.PanelError(result.get('reason', 'deployment_rejected'))
                return result
        # Raw Terminal output can contain account paths; never include it in errors.
        raise panel.PanelError('deployment_timeout')


def release():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]


def deploy(session, root, operation, backup_id=''):
    verified = inventory.terminal_inventory(session, root)
    if verified.get('active_stylesheet') != 'kadence' or int(verified.get('front_page_id', 0)) != 42:
        raise panel.PanelError('site_configuration_changed')
    config = json.loads((ROOT / 'content/catalog.json').read_text())
    payload = {'operation': operation, 'release': release()}
    if operation == 'styles':
        payload['css'] = (ROOT/'wordpress/brincolines-landing/landing.css').read_text()
    if operation == 'rollback':
        if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{12}', backup_id):
            raise panel.PanelError('invalid_backup_id')
        payload['backup_id'] = backup_id
    if operation in {'draft', 'publish'}:
        manifest = {}
        if operation == 'publish':
            photos = {}
            for model in config['models']:
                path = ROOT / 'assets/catalog' / (model['slug'] + '.webp')
                if not path.is_file():
                    continue
                if path.is_symlink():
                    raise panel.PanelError('photo_symlink_rejected')
                data = path.read_bytes()
                if not 100 < len(data) < 1_500_000:
                    raise panel.PanelError('photo_size_rejected')
                photos[model['slug']] = dict(bytes=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest(), title=model['name'], alt=model['alt'])
            if config['hero'] not in photos:
                raise panel.PanelError('original_hero_photo_file_required')
            imported = terminal_operation(session, root, {'operation': 'import', 'release': release(), 'photos': photos})
            manifest = imported['manifest']
        content, missing = builder.build(config, manifest, draft=operation == 'draft')
        payload.update(content=content, manifest=manifest, plugin_files={name:(ROOT/'wordpress/brincolines-landing'/name).read_text() for name in ['brincolines-landing.php','landing.css']})
    result=terminal_operation(session, root, payload)
    if operation in {'draft','publish'}:
        result['missing_original_photos']=missing
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup','draft','publish','styles','rollback'])
    parser.add_argument('--backup-id', default='')
    parser.add_argument('--interactive', action='store_true')
    args = parser.parse_args()
    report = {'domain': panel.DOMAIN, 'operation': args.operation, 'ok': False}
    try:
        user = os.environ.get('BH_USER', '')
        password = os.environ.get('BH_CPANEL_PASSWORD', '')
        if args.interactive:
            user = getpass.getpass('Usuario cPanel (entrada oculta): ')
            password = getpass.getpass('Contraseña cPanel (entrada oculta): ')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user) or not password:
            raise panel.PanelError('existing_cpanel_credentials_missing')
        session = panel.PanelSession(user, password)
        password = ''
        root = panel.validate_domain(session.api_call('DomainInfo','single_domain_data',{'domain':panel.DOMAIN}))
        files = session.api_call('Fileman','list_files',{'dir':root})
        names = {item.get('file',item.get('name','')) for item in files}
        if not {'wp-load.php','wp-settings.php','wp-includes','wp-content'}.issubset(names):
            raise panel.PanelError('wordpress_files_not_verified')
        report.update(deploy(session, root, args.operation, args.backup_id))
    except panel.PanelError as error:
        report['reason'] = str(error)
    except Exception as error:
        report['error_type'] = type(error).__name__
    output = ROOT / '.local/landing'
    output.mkdir(parents=True,exist_ok=True)
    (output/'deployment-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,separators=(',',':')))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
