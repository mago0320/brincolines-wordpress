# Brincolines Jumping · WordPress existente

El sitio de producción es **https://brincolinesjumping.com/**. Su HTML público referencia Kadence; la confirmación del tema activo requiere el inventario SSH. Se conserva el tema y el diseño existentes. Este repositorio no instala WordPress ni crea otro tema.

## Acceso desde GitHub Actions

`BanaHosting - localizar WordPress` se ejecuta únicamente con `workflow_dispatch`. Comprueba la identidad SSH, inicia sesión con la clave autorizada en cPanel y busca exactamente el dominio permitido. Primero usa la ruta configurada, si existe; después consulta los metadatos de ese dominio en cPanel y, si no están disponibles, busca instalaciones en HOME. Solo inventaría la coincidencia única de `home` con `brincolinesjumping.com` o `www.brincolinesjumping.com`.

El artifact `banahost-wordpress-inventory-<run_id>` dura un día y contiene usuario, hostname, HOME, ruta WordPress, dominio, versiones, rutas de temas, tema activo y plugins. Nunca incluye claves, contraseñas ni el contenido de `wp-config.php`. Durante el descubrimiento solo se consultan metadatos para distinguir instalaciones; no se editan archivos ni bases de datos.

### Secrets compatibles

El workflow reutiliza los secrets ya creados. No es necesario recrearlos si usan estos alias.

| Uso | Nombre principal | Alias admitidos |
| --- | --- | --- |
| Host SSH | `BANAHOST_SSH_HOST` | `BANAHOST_HOST`, `SSH_HOST` |
| Usuario SSH | `BANAHOST_SSH_USER` | `BANAHOST_USER`, `SSH_USER`, `SSH_USERNAME` |
| Clave privada | `BANAHOST_SSH_PRIVATE_KEY` | `BANAHOST_SSH_KEY`, `BANAHOST_PRIVATE_KEY`, `BANAHOST_KEY`, `SSH_PRIVATE_KEY`, `SSH_KEY` |
| Puerto (22 si no está configurado) | `BANAHOST_SSH_PORT` | `BANAHOST_PORT`, `SSH_PORT` |
| Ruta opcional de WordPress | `BANAHOST_WP_PATH` | `BANAHOST_PATH`, `WP_PATH`, `SSH_PATH`; también variable `BANAHOST_WP_PATH` |
| Claves públicas verificadas del servidor | `BANAHOST_SSH_KNOWN_HOSTS` | `BANAHOST_KNOWN_HOSTS`, `SSH_KNOWN_HOSTS` |
| Alternativa: huella SHA256 verificada del servidor | `BANAHOST_SSH_FINGERPRINT` | `BANAHOST_FINGERPRINT`, `SSH_HOST_FINGERPRINT`, `SSH_FINGERPRINT` |
| Passphrase, solo si la clave está cifrada | `BANAHOST_SSH_PASSPHRASE` | `BANAHOST_PASSPHRASE`, `SSH_PASSPHRASE` |

Las claves autorizadas se obtienen en cPanel → Acceso SSH → Administrar claves SSH. El secret de clave privada contiene la clave completa, incluidos encabezado y cierre; no la clave pública. La confianza del servidor usa `known_hosts` o una huella SHA256 comprobada con BanaHosting. Si falta, el workflow consulta las huellas públicas, las conserva para verificación y se detiene antes de autenticarse. Una clave escaneada no se acepta automáticamente como verificada.

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
