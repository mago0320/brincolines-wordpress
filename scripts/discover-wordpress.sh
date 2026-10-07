#!/usr/bin/env bash
# Runs through SSH stdin. Inventory only: no installation, activation, SQL
# mutation, file creation or edits on the remote account.
set -euo pipefail
target=${1:-}
hint=${2:-}
[[ $target == brincolinesjumping.com ]] || { echo 'Dominio fuera del alcance autorizado.' >&2; exit 2; }
for tool in php realpath find; do
  command -v "$tool" >/dev/null || { echo "Falta herramienta remota: $tool" >&2; exit 2; }
done
wp_cli=$(command -v wp || true)
if [[ -z $wp_cli ]]; then
  for binary in /usr/local/bin/wp "$HOME/bin/wp" "$HOME/wp-cli.phar"; do
    if [[ -x $binary ]]; then wp_cli=$binary; break; fi
  done
fi
[[ -n $wp_cli ]] || { echo 'WP-CLI no se encuentra en PATH ni en las rutas habituales.' >&2; exit 2; }
account_home=$(realpath -e -- "$HOME")
matches=()
seen=()

hostname_matches() {
  php -r '$u=parse_url(trim(stream_get_contents(STDIN)), PHP_URL_HOST); $h=strtolower(rtrim((string)$u,".")); exit(in_array($h,[$argv[1],"www.".$argv[1]],true)?0:1);' "$target"
}

inspect_root() {
  local proposed=$1 root prior home_url
  [[ -d $proposed ]] || return 0
  root=$(realpath -e -- "$proposed") || return 0
  [[ $root == "$account_home/"* ]] || return 0
  [[ -f $root/wp-load.php && -d $root/wp-includes && -f $root/wp-settings.php ]] || return 0
  for prior in "${seen[@]}"; do [[ $prior != "$root" ]] || return 0; done
  seen+=("$root")
  # Skip regular plugins/themes, and never emit URLs of other installations.
  if home_url=$("$wp_cli" --path="$root" --skip-plugins --skip-themes --no-color option get home 2>/dev/null) &&
     hostname_matches <<< "$home_url"; then
    matches+=("$root")
  fi
}

scan_under() {
  local base=$1 depth=$2 fd pid loader
  exec {fd}< <(find "$base" -maxdepth "$depth" -type d \( -name wp-content -o -name .git -o -name mail -o -name .cpanel -o -name .trash -o -name logs \) -prune -o -type f -name wp-load.php -print0)
  pid=$!
  while IFS= read -r -d '' loader; do inspect_root "${loader%/wp-load.php}"; done <&"$fd"
  exec {fd}<&-
  wait "$pid" || { echo 'La búsqueda de instalaciones quedó incompleta; se canceló el inventario.' >&2; exit 3; }
}

if [[ -n $hint ]]; then
  [[ $hint == /* ]] || { echo 'La ruta WordPress debe ser absoluta.' >&2; exit 2; }
  inspect_root "$hint"
  [[ ${#matches[@]} == 1 ]] || { echo 'La ruta configurada no corresponde al WordPress del dominio autorizado.' >&2; exit 3; }
else
  # Prefer cPanel's exact-domain metadata rather than guessing a hosting layout.
  uapi=$(command -v uapi || true)
  [[ -n $uapi || ! -x /usr/local/cpanel/bin/uapi ]] || uapi=/usr/local/cpanel/bin/uapi
  document_root=''
  if [[ -n $uapi ]]; then
    document_root=$("$uapi" --output=json DomainInfo single_domain_data "domain=$target" 2>/dev/null |
      php -r '$j=json_decode(stream_get_contents(STDIN),true); $p=$j["result"]["data"]["documentroot"]??""; if(is_string($p)) echo $p;' || true)
  fi
  if [[ -n $document_root ]]; then
    inspect_root "$document_root"
    if [[ ${#matches[@]} == 0 && -d $document_root ]]; then
      scan_under "$document_root" 4
    fi
  else
    for candidate in "$HOME/public_html" "$HOME/$target" "$HOME/public_html/$target" "$HOME/domains/$target/public_html"; do
      inspect_root "$candidate"
    done
    # Metadata discovery can visit account directories, but does not alter or
    # inventory other sites. Only matched roots can reach the inventory below.
    scan_under "$HOME" 7
  fi
fi

if [[ ${#matches[@]} != 1 ]]; then
  printf 'Se encontraron %s instalaciones coincidentes; se exige exactamente una antes de administrar el sitio.\n' "${#matches[@]}" >&2
  exit 3
fi
root=${matches[0]}
if "$wp_cli" --path="$root" --skip-plugins --skip-themes config is-true MULTISITE >/dev/null 2>&1; then
  echo 'La instalación es multisite. Hace falta acotar el sitio/blog antes de administrarlo.' >&2
  exit 3
fi
export BJ_AUDIT_DOMAIN="$target" BJ_AUDIT_HOME="$account_home" BJ_AUDIT_ROOT="$root"
BJ_AUDIT_USER=$(whoami)
BJ_AUDIT_HOST=$(hostname)
export BJ_AUDIT_USER BJ_AUDIT_HOST

"$wp_cli" --path="$root" --skip-plugins --skip-themes --no-color eval '
$target = getenv("BJ_AUDIT_DOMAIN");
$actual = strtolower(rtrim((string)parse_url(get_option("home"), PHP_URL_HOST), "."));
if (!in_array($actual, array($target, "www." . $target), true) || is_multisite()) {
    fwrite(STDERR, "El dominio cambió o la instalación es multisite.\n"); exit(3);
}
require_once ABSPATH . "wp-admin/includes/plugin.php";
$themes = array();
foreach (wp_get_themes() as $slug => $theme) {
    $themes[] = array("slug" => $slug, "name" => $theme->get("Name"), "version" => $theme->get("Version"), "parent" => $theme->get("Template"));
}
$plugins = array();
foreach (get_plugins() as $file => $plugin) {
    $plugins[] = array("file" => $file, "name" => $plugin["Name"], "version" => $plugin["Version"], "active" => is_plugin_active($file));
}
$content = realpath(WP_CONTENT_DIR);
$themes_dir = realpath(get_theme_root());
$report = array(
    "target_domain" => $target, "match_verified" => true,
    "ssh_user" => getenv("BJ_AUDIT_USER"), "hostname" => getenv("BJ_AUDIT_HOST"),
    "home_dir" => getenv("BJ_AUDIT_HOME"), "wordpress_root" => realpath(ABSPATH),
    "home_url" => get_option("home"), "site_url" => get_option("siteurl"),
    "wordpress_version" => get_bloginfo("version"), "php_version" => PHP_VERSION,
    "content_dir" => $content, "themes_dir" => $themes_dir,
    "active_template" => get_option("template"), "active_stylesheet" => get_option("stylesheet"),
    "themes" => $themes, "plugins" => $plugins,
    "front_page_id" => (int)get_option("page_on_front"), "show_on_front" => get_option("show_on_front"),
    "checks" => array("theme_directory_inside_wordpress" => is_string($themes_dir) && strpos($themes_dir, realpath(ABSPATH) . DIRECTORY_SEPARATOR) === 0)
);
echo wp_json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
'
