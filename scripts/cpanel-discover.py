#!/usr/bin/env python3
"""Read-only, HTTPS-verified cPanel discovery for one authorized domain."""
import base64
import getpass
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import sys
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


def normalize_login_password(password):
    # A pasted secret may end with Enter. Preserve spaces and all password
    # characters; remove only terminal CR/LF, which are not part of this login.
    normalized = password.rstrip('\r\n')
    if '\r' in normalized or '\n' in normalized:
        raise PanelError('password_contains_embedded_linebreak')
    return normalized


class PanelSession:
    """Keep a verified cPanel web session in memory on the fixed origin only."""
    def __init__(self, user, password):
        password = normalize_login_password(password)
        self.base = 'https://' + HOST + ':2083'
        # Follow the normal browser login sequence. Keep the pre-login cookie
        # only in memory and explicitly scoped to the same verified origin.
        with secure_open(urllib.request.Request(self.base + '/')) as response:
            prelogin = SimpleCookie()
            for header in response.headers.get_all('Set-Cookie', []):
                prelogin.load(header)
            response.read(2_000_000)
        headers = {'Accept': 'application/json', 'Origin': self.base,
                   'Referer': self.base + '/', 'Content-Type': 'application/x-www-form-urlencoded'}
        if prelogin.get('cprelogin') and prelogin['cprelogin'].value:
            headers['Cookie'] = 'cprelogin=' + prelogin['cprelogin'].coded_value
        request = urllib.request.Request(self.base + '/login/?login_only=1',
            data=urllib.parse.urlencode({'user': user, 'pass': password}).encode(),
            headers=headers)
        try:
            with secure_open(request) as response:
                cookies = SimpleCookie()
                for header in response.headers.get_all('Set-Cookie', []):
                    cookies.load(header)
                payload = json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as error:
            # Diagnose known rejection classes without logging response bodies,
            # which can reflect credentials. Never retry a rejected login here.
            error.cpanel_reason = 'login_http_rejected'
            try:
                rejection = json.loads(error.read(32_000))
                if isinstance(rejection, dict):
                    if rejection.get('tfa_required') or rejection.get('twofactor_required'):
                        error.cpanel_reason = 'cpanel_two_factor_required'
                    elif rejection.get('status') == 0 and rejection.get('message') == 'The login is invalid.':
                        error.cpanel_reason = 'cpanel_credentials_rejected'
            except (ValueError, TypeError, OSError):
                pass
            raise
        if payload.get('tfa_required') or payload.get('twofactor_required'):
            raise PanelError('cpanel_two_factor_required')
        if payload.get('status') != 1:
            raise PanelError('cpanel_login_rejected')
        self.session = payload.get('security_token', '')
        if not isinstance(self.session, str) or not re.fullmatch(r'/cpsess[0-9]+', self.session):
            raise PanelError('unexpected_session_token')
        cookie = cookies.get('cpsession')
        if cookie is None or not cookie.value:
            raise PanelError('missing_session_cookie')
        # Explicitly scope this cookie to the fixed HTTPS origin. cPanel's port
        # attribute can cause standard cookie jars to reject it behind a proxy.
        self.cookie = 'cpsession=' + cookie.coded_value

    def api_call(self, module, function, params):
        scoped_endpoint = endpoint(module, function, params)
        request = urllib.request.Request(self.base + self.session + scoped_endpoint[len(self.base):],
            headers={'Accept': 'application/json', 'Cookie': self.cookie})
        with secure_open(request) as response:
            payload = json.loads(response.read(2_000_000))
        result = payload.get('result', payload)
        if result.get('status') != 1:
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
                          status='requires_cpanel_authentication')
            return report
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user):
            raise PanelError('missing_or_invalid_cpanel_user')
        credential = token or password
        auth_options = {'password_auth':True} if not token else {}
        def call(module, function, params):
            return api_call(user, credential, module, function, params, **auth_options)
        try:
            data = call('DomainInfo', 'single_domain_data', {'domain': DOMAIN})
            report['authentication_method'] = 'api_token' if token else 'basic_https'
        except urllib.error.HTTPError as error:
            if error.code != 401 or token or not password:
                raise
            session = PanelSession(user, password)
            call = session.api_call
            data = call('DomainInfo', 'single_domain_data', {'domain': DOMAIN})
            report['authentication_method'] = 'cpanel_web_session'
        root = validate_domain(data)
        report.update(authenticated=True, endpoint_reachable=True, tls_verified=True, documentroot=root)
        files = call('Fileman', 'list_files', {'dir': root})
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
    user=os.environ.get('BH_USER', '')
    token=os.environ.get('BH_CPANEL_TOKEN', '')
    password=os.environ.get('BH_CPANEL_PASSWORD', '')
    if '--interactive' in sys.argv:
        user=getpass.getpass('Usuario cPanel (entrada oculta): ')
        password=getpass.getpass('Contraseña cPanel (entrada oculta): ')
        token=''
    report = discover(user, token, password)
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        # Public repository artifacts must not reveal account names in paths.
        for field in ('documentroot','wordpress_root_candidate'):
            if report.get(field): report[field]='[private]'
    output = Path('.local/audit')
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    report_file = output / 'cpanel-discovery.json'
    report_file.write_text(json.dumps(report, indent=2) + '\n')
    report_file.chmod(0o600)
    print('::notice title=Alternativa cPanel HTTPS::' + json.dumps(report, separators=(',', ':')))


if __name__ == '__main__':
    main()
