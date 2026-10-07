# Brincolines Jumping · WordPress existente

El sitio de producción es **https://brincolinesjumping.com/**. Su HTML público referencia Kadence; la confirmación del tema activo requiere el inventario SSH. Se conserva el tema y el diseño existentes. Este repositorio no instala WordPress ni crea otro tema.

## Acceso desde GitHub Actions

`BanaHosting - localizar WordPress` se ejecuta únicamente con `workflow_dispatch`. Comprueba la identidad SSH, inicia sesión con la clave autorizada en cPanel y busca exactamente el dominio permitido. Primero usa la ruta configurada, si existe; después consulta los metadatos de ese dominio en cPanel y, si no están disponibles, busca instalaciones en HOME. Solo inventaría la coincidencia única de `home` con `brincolinesjumping.com` o `www.brincolinesjumping.com`.

El artifact `banahost-wordpress-inventory-<run_id>` dura un día y contiene usuario, hostname, HOME, ruta WordPress, dominio, versiones, rutas de temas, tema activo y plugins. Nunca incluye claves, contraseñas ni el contenido de `wp-config.php`. Durante el descubrimiento solo se consultan metadatos para distinguir instalaciones; no se editan archivos ni bases de datos.

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

El primer requisito para la alternativa de cPanel es **un token API**, generado en cPanel → Seguridad → Administrar tokens API y guardado en GitHub → Settings → Secrets and variables → Actions como `BANAHOST_CPANEL_API_TOKEN`. El token se introduce solo en ese campo seguro. El flujo automatizado inspeccionará las capacidades disponibles antes de decidir si también hace falta una credencial específica de WordPress. No asumas que un token de cPanel permite ejecutar WP-CLI: esa capacidad debe comprobarse en las herramientas realmente disponibles del panel.

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
