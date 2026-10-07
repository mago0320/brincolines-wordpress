# Brincolines Jumping · WordPress existente

El sitio de producción es **https://brincolinesjumping.com/**. WP-CLI confirmó **Kadence** como tema activo, portada estática ID **42** y metadatos Elementor presentes. Actualmente no hay plugins activos; antes de editar la portada debe revisarse esa situación y conservarse su contenido y diseño. Este repositorio no instala WordPress ni crea otro tema.

## Acceso verificado sin SSH externo

Desde Cloud funciona el inicio de sesión HTTPS de cPanel y su Terminal por WebSocket, con certificados verificados. WP-CLI ejecutado por esa Terminal confirmó `home` y `siteurl` del dominio autorizado y descartó multisite. El puerto SSH externo sigue rechazando la conexión; no es necesario seguir probando puertos.

`scripts/cpanel-wordpress.py` reproduce el inventario de forma autónoma. Comprueba primero el documentroot de este dominio y los archivos WordPress; después revalida las URL desde WP-CLI antes de leer opciones. Omite el arranque de plugins y temas durante la consulta. Sus informes no contienen rutas de cuenta, contraseñas ni cookies. La sesión y sus credenciales permanecen en memoria.

El workflow manual **BanaHosting - WordPress por cPanel HTTPS** usa esta vía y no prueba ningún puerto SSH. Reutiliza el usuario guardado en los secrets existentes y necesita `BANAHOST_CPANEL_PASSWORD` (también admite `BANAHOST_PASSWORD` o `CPANEL_PASSWORD`). La integración de GitHub disponible en Cloud no permite escribir secrets: ese binding debe introducirse en Settings → Secrets and variables → Actions. La verificación desde Cloud ya funciona con las credenciales proporcionadas privadamente; la disponibilidad del binding en Actions se comprueba por separado. El workflow actual solo inventaría, sin desplegar ni modificar producción.

## Acceso desde GitHub Actions

`BanaHosting - localizar WordPress` se ejecuta únicamente con `workflow_dispatch`. Comprueba la identidad SSH, inicia sesión con la clave autorizada en cPanel y busca exactamente el dominio permitido. Primero usa la ruta configurada, si existe; después consulta los metadatos de ese dominio en cPanel y, si no están disponibles, busca instalaciones en HOME. Solo inventaría la coincidencia única de `home` con `brincolinesjumping.com` o `www.brincolinesjumping.com`.

El artifact `banahost-wordpress-inventory-<run_id>` dura un día y contiene resultados de conexión y metadatos del sitio. Los informes públicos ocultan usuario, HOME y rutas que pueden identificar la cuenta. Nunca incluyen claves, contraseñas ni el contenido de `wp-config.php`. Durante el descubrimiento solo se consultan metadatos para distinguir instalaciones; no se editan archivos ni bases de datos.

### Secrets compatibles

El endpoint confirmado por el usuario es **single-4650.banahosting.com:22**. El workflow reutiliza `BANAHOST_SSH_HOST`, actualizado por el usuario; si falta, usa ese hostname público como fallback. Prueba primero el puerto 22. Los demás secrets se reutilizan con estos alias.

El diagnóstico comprueba exclusivamente el host y puerto indicados. No busca puertos alternativos. El input `ssh_host` admite el hostname oficial o su IP `50.31.167.146`. `probe_only=true` hace la comprobación TCP sin intentar autenticación SSH.

El input manual `ssh_port` permite comprobar un puerto indicado por el usuario. Para un puerto distinto de 22 se comprueba solo ese puerto, incluido 4650; no hace falta editar los secrets ni el workflow para ejecutar esa prueba.

| Uso | Nombre principal | Alias admitidos |
| --- | --- | --- |
| Usuario SSH | `BANAHOST_SSH_USER` | `BANAHOST_USER`, `SSH_USER`, `SSH_USERNAME` |
| Clave privada | `BANAHOST_SSH_PRIVATE_KEY` | `BANAHOST_SSH_KEY`, `BANAHOST_PRIVATE_KEY`, `BANAHOST_KEY`, `SSH_PRIVATE_KEY`, `SSH_KEY` |
| Ruta opcional de WordPress | `BANAHOST_WP_PATH` | `BANAHOST_PATH`, `WP_PATH`, `SSH_PATH`; también variable `BANAHOST_WP_PATH` |
| Claves públicas verificadas del servidor | `BANAHOST_SSH_KNOWN_HOSTS` | `BANAHOST_KNOWN_HOSTS`, `SSH_KNOWN_HOSTS` |
| Alternativa: huella SHA256 verificada del servidor | `BANAHOST_SSH_FINGERPRINT` | `BANAHOST_FINGERPRINT`, `SSH_HOST_FINGERPRINT`, `SSH_FINGERPRINT` |
| Passphrase, solo si la clave está cifrada | `BANAHOST_SSH_PASSPHRASE` | `BANAHOST_PASSPHRASE`, `SSH_PASSPHRASE` |

Las claves autorizadas se obtienen en cPanel → Acceso SSH → Administrar claves SSH. El secret de clave privada contiene la clave completa, incluidos encabezado y cierre; no la clave pública. La confianza del servidor usa `known_hosts` o una huella SHA256 comprobada con BanaHosting. Si falta, el workflow consulta las huellas públicas, las conserva para verificación y se detiene antes de autenticarse. Una clave escaneada no se acepta automáticamente como verificada.

El diagnóstico previo diferencia DNS, conexión TCP rechazada, timeout, cierre antes de la cabecera y respuesta SSH. Una cabecera SSH demuestra que el servicio es accesible desde ese runner. Un rechazo o timeout por sí solo no prueba que el plan de hosting prohíba SSH: esa política debe confirmarse con BanaHosting.

### Alternativa sin SSH: cPanel HTTPS y WordPress REST

`scripts/cpanel-discover.py` comprueba HTTPS con verificación de certificado en el servidor oficial, puerto 2083. Si existe `BANAHOST_CPANEL_API_TOKEN`, reutiliza el usuario cPanel/SSH ya configurado, consulta únicamente los metadatos de `brincolinesjumping.com` y lista su documentroot para detectar archivos WordPress. No modifica archivos ni lee `wp-config.php`. El workflow conserva el resultado; no se envían ni registran valores de tokens.

La API pública de WordPress confirmó soporte para contraseñas de aplicación y endpoints de páginas y plugins. Las operaciones de escritura requieren autenticación y capacidades del usuario. El sitio usa Elementor: no debe reemplazarse su contenido de forma que se pierda el diseño o los metadatos del editor.

La alternativa admite token API o autenticación con contraseña por HTTPS. En una máquina cloud autorizada se puede ejecutar `python3 scripts/cpanel-discover.py --interactive`: ambas entradas quedan ocultas y sus valores se usan solo en memoria para la petición al servidor oficial. Los valores no se escriben en archivos, argumentos de comandos ni informes. En Actions se reutilizan bindings privados `BANAHOST_CPANEL_API_TOKEN` o `BANAHOST_CPANEL_PASSWORD` si ya existen. No se exige crear otra credencial cuando ya se dispone de una utilizable. El flujo inspeccionará las capacidades disponibles antes de decidir si también hace falta autenticación específica de WordPress. No asumas que cPanel permite ejecutar WP-CLI: esa capacidad debe comprobarse en las herramientas realmente disponibles del panel.

El acceso real desde Cloud se verificó mediante la sesión web de cPanel: autenticación aceptada, dominio y documentroot comprobados y archivos WordPress presentes. Cuando Basic Auth devuelve 401, el script inicia esa sesión con la misma contraseña y consulta la API mediante su cookie en memoria. Solo envía la cookie al origen HTTPS oficial y rechaza redirecciones. Los informes locales tienen permisos privados; los artifacts públicos ocultan las rutas de cuenta. Esta verificación de Cloud no demuestra que Actions tenga los bindings de cPanel disponibles.

Los secrets se introducen solo en GitHub → repositorio → Settings → Secrets and variables → Actions; nunca en el código ni en el chat. Si existen únicamente como secrets de un Environment de GitHub, el job debe vincularse a ese Environment antes de usarlos.

## Alcance de administración

El usuario autoriza administrar el WordPress de este dominio, manteniendo el tema actual y realizando ajustes pequeños para completar la web. Esa autorización no se extiende a otros dominios de la cuenta. Antes de cambiar producción, debe verificarse la coincidencia de dominio y guardarse una copia recuperable de los archivos o contenido que se vaya a cambiar. La autorización amplia no exige cambiar componentes que no lo necesitan.

Este primer workflow es exclusivamente de inventario: no instala, actualiza, activa, desactiva ni elimina temas o plugins; no cambia páginas, opciones ni base de datos. No hay despliegues automáticos en cada commit.

## Validación local

```bash
bash -n scripts/ssh-discover.sh scripts/discover-wordpress.sh
python3 -m unittest discover -s tests -v
```

Las pruebas usan un hosting y WP-CLI simulados para comprobar que los dominios ajenos se excluyen, las rutas se validan y las coincidencias ambiguas se rechazan. La conexión real requiere que el workflow termine correctamente; las pruebas locales por sí solas no la demuestran.
