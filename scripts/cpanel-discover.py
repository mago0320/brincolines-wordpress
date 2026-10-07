#!/usr/bin/env python3
"""Read-only, HTTPS-verified cPanel discovery for one authorized domain."""
import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

HOST = 'single-4650.banahosting.com'
DOMAIN = 'brincolinesjumping.com'


class PanelError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Credentials must never follow redirects to another endpoint.
        return None


def secure_open(request):
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    return opener.open(request, timeout=20)


def endpoint(module, function, params):
    if (module, function) not in {('DomainInfo', 'single_domain_data'), ('Fileman', 'list_files')}:
        raise PanelError('api_operation_out_of_scope')
    return 'https://' + HOST + ':2083/execute/' + module + '/' + function + '?' + urllib.parse.urlencode(params)


def api_call(user, token, module, function, params, password_auth=False):
    authorization = 'cpanel ' + user + ':' + token
    if password_auth:
        authorization = 'Basic ' + base64.b64encode((user + ':' + token).encode()).decode('ascii')
    request = urllib.request.Request(endpoint(module, function, params), headers={
        'Authorization': authorization,
        'Accept': 'application/json',
    })
    with secure_open(request) as response:
        payload = json.loads(response.read(2_000_000))
    result = payload.get('result', payload)
    if result.get('status') != 1:
        # Never expose arbitrary API error bodies: they may reflect credentials.
        raise PanelError('cpanel_api_operation_rejected')
    return result.get('data')


def validate_domain(data):
    if not isinstance(data, dict) or data.get('domain', '').lower().rstrip('.') != DOMAIN:
        raise PanelError('returned_domain_out_of_scope')
    root = data.get('documentroot', '')
    if not isinstance(root, str) or not root.startswith('/') or any(p in ('.', '..') for p in root.split('/')) or any(c in root for c in '\r\n\0'):
        raise PanelError('unsafe_documentroot')
    if root == '/':
        raise PanelError('unsafe_documentroot')
    return str(PurePosixPath(root))


def discover(user, token, password=''):
    report = {'cpanel_host': HOST, 'target_domain': DOMAIN, 'token_present': bool(token), 'password_present':bool(password), 'authenticated': False}
    try:
        if not token and not password:
            # No authentication attempt. A valid HTTPS response establishes the
            # panel endpoint is reachable; it does not establish API permissions.
            request = urllib.request.Request(endpoint('DomainInfo', 'single_domain_data', {'domain': DOMAIN}))
            try:
                with secure_open(request) as response:
                    status = response.status
            except urllib.error.HTTPError as error:
                status = error.code
            report.update(endpoint_reachable=True, tls_verified=True, http_status=status,
                          status='requires_cpanel_api_token', required_secret='BANAHOST_CPANEL_API_TOKEN')
            return report
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user):
            raise PanelError('missing_or_invalid_cpanel_user')
        credential = token or password
        auth_options = {'password_auth':True} if not token else {}
        data = api_call(user, credential, 'DomainInfo', 'single_domain_data', {'domain': DOMAIN}, **auth_options)
        root = validate_domain(data)
        report.update(authenticated=True, endpoint_reachable=True, tls_verified=True, documentroot=root)
        files = api_call(user, credential, 'Fileman', 'list_files', {'dir': root}, **auth_options)
        if not isinstance(files, list):
            raise PanelError('unexpected_directory_listing')
        names = {str(item.get('file', item.get('name', ''))) for item in files if isinstance(item, dict)}
        found = {'wp-load.php', 'wp-settings.php', 'wp-includes', 'wp-content'}.issubset(names)
        report.update(wordpress_files_present=found, wordpress_root_candidate=root if found else None,
                      status='domain_documentroot_verified')
    except urllib.error.HTTPError as error:
        report.update(status='http_error', http_status=error.code)
    except urllib.error.URLError as error:
        reason = error.reason
        report['status'] = 'tls_verification_failed' if isinstance(reason, ssl.SSLCertVerificationError) else 'https_connection_failed'
    except (TimeoutError, ssl.SSLError):
        report['status'] = 'https_connection_failed'
    except PanelError as error:
        report.update(status='cpanel_discovery_blocked', reason=str(error))
    except (ValueError, TypeError, OSError):
        report['status'] = 'invalid_api_response_or_configuration'
    return report


def main():
    report = discover(os.environ.get('BH_USER', ''), os.environ.get('BH_CPANEL_TOKEN', ''), os.environ.get('BH_CPANEL_PASSWORD', ''))
    output = Path('.local/audit')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'cpanel-discovery.json').write_text(json.dumps(report, indent=2) + '\n')
    print('::notice title=Alternativa cPanel HTTPS::' + json.dumps(report, separators=(',', ':')))


if __name__ == '__main__':
    main()
