# Brincolines Jumping · WordPress existente

El sitio de producción es **https://brincolinesjumping.com/**. WP-CLI confirmó **Kadence** como tema activo, portada estática ID **42** y metadatos Elementor presentes. Actualmente no hay plugins activos; antes de editar la portada debe revisarse esa situación y conservarse su contenido y diseño. Este repositorio no instala WordPress ni crea otro tema.

## Acceso verificado sin SSH externo

Desde Cloud funciona el inicio de sesión HTTPS de cPanel y su Terminal por WebSocket, con certificados verificados. WP-CLI ejecutado por esa Terminal confirmó `home` y `siteurl` del dominio autorizado y descartó multisite. El puerto SSH externo sigue rechazando la conexión; no es necesario seguir probando puertos.

`scripts/cpanel-wordpress.py` reproduce el inventario de forma autónoma. Comprueba primero el documentroot de este dominio y los archivos WordPress; después revalida las URL desde WP-CLI antes de leer opciones. Omite el arranque de plugins y temas durante la consulta. Sus informes no contienen rutas de cuenta, contraseñas ni cookies. La sesión y sus credenciales permanecen en memoria.

El workflow manual **BanaHosting - WordPress por cPanel HTTPS** usa esta vía y no prueba ningún puerto SSH. Reutiliza el usuario guardado en los secrets existentes y `BANAHOST_CPANEL_PASSWORD` (también admite `BANAHOST_PASSWORD` o `CPANEL_PASSWORD`). El acceso real desde Actions quedó verificado en la [ejecución 37680310022](https://github.com/mago0320/brincolines-wordpress/actions/runs/37680310022): inicio de sesión, dominio, archivos WordPress y WP-CLI correctos, Kadence activo y sin multisite. El workflow actual solo inventaría, sin desplegar ni modificar producción.

El cliente sigue el flujo de inicio de sesión del navegador, conservando la cookie previa solo en memoria. Elimina únicamente saltos de línea CR/LF finales que puedan añadirse al pegar la contraseña; conserva espacios y rechaza saltos de línea internos antes de autenticar. El diagnóstico identifica la etapa y señales conocidas del rechazo sin publicar el cuerpo de errores, credenciales ni cookies. Las 26 pruebas de cPanel pasaron tanto localmente como en la ejecución verificada de Actions.

## Landing móvil con Kadence y Gutenberg

El WhatsApp confirmado por el propietario es **449 191 1663** (`524491911663`). El catálogo de ocho modelos está en `content/catalog.json`. No se utilizan las tarifas, teléfonos antiguos ni testimonios del mockup.

`wordpress/brincolines-landing/` contiene un complemento pequeño de CSS y SEO aislado. Conserva Kadence y usa bloques nativos editables: grupos, títulos, párrafos, imágenes, botones y acordeones. No incorpora otro constructor, fuentes remotas ni JavaScript propio.

El workflow **Brincolines Jumping - Landing manual** se ejecuta únicamente con `workflow_dispatch`. Reutiliza los mismos secrets y transporte HTTPS verificado del inventario anterior. Valida PHP, bloques y restricciones antes de aplicar una operación. Revalida dominio, documentroot, ausencia de multisite, Kadence y portada ID 42.

| Operación | Efecto |
| --- | --- |
| `backup` | Copia privada recuperable de las páginas afectadas, metadatos, opciones y archivos del complemento. |
| `draft` | Crea o actualiza una página borrador editable; conserva la portada pública. Las fotos pendientes están rotuladas únicamente en este borrador. |
| `publish` | Importa fotografías reales disponibles, crea variantes en Media Library, reemplaza la portada 42 y retira la página Contact Us de demostración con redirección a `/#contacto`. Requiere la fotografía real principal. |
| `rollback` | Restaura el respaldo indicado; se detiene si detecta ediciones posteriores. Conserva los archivos añadidos, sin borrarlos. |

Los respaldos se guardan en una carpeta privada de la cuenta fuera del directorio público, con permisos 700/600 y SHA-256 verificado antes de escribir. Los artifacts de Actions contienen solo el informe resumido y el ID de respaldo, nunca el contenido original, rutas de cuenta, credenciales ni cookies. La copia local privada permanece en `.local/landing/backups/` y está ignorada por Git.

Antes de publicar, las fotos reales revisadas y optimizadas deben existir en `assets/catalog/<slug>.webp`. Si falta una imagen secundaria se registra como pendiente y no se publica una imagen ficticia ni un recuadro de espera. Si falta el hero real, la publicación se detiene. El cliente genera `srcset`, dimensiones y variantes mediante WordPress; el hero carga inmediatamente y las imágenes inferiores usan lazy loading.

Los enlaces de WhatsApp incluyen el modelo seleccionado. El SEO de la portada contempla un único H1, title, descripción, canonical nativo, Open Graph y datos LocalBusiness/Service con nombre, teléfono y Aguascalientes, sin dirección, estrellas ni horarios inventados.

## Editar sin programar

En WordPress → Páginas, abre **Brincolines Jumping**. La vista de lista del editor permite encontrar cada sección. Pulsa un texto para editarlo, una imagen para reemplazarla desde Biblioteca de medios o un botón para cambiar su enlace. Guarda el borrador o actualiza la portada según su estado. Las nuevas fotos conservan la composición mediante `object-fit: contain`.

## Validación

```bash
.local/venv/bin/python -m unittest discover -s tests -p 'test_cpanel*.py' -v
.local/venv/bin/python -m unittest discover -s tests -p 'test_landing*.py' -v
php -l scripts/landing-operation.php
php -l wordpress/brincolines-landing/brincolines-landing.php
python3 scripts/build-landing.py --draft
```

La validación visual se realiza a 375, 390, 430, 768 y 1440 px, comprobando desbordamientos, un único H1, enlaces, botones táctiles y acordeones con teclado. Una captura de borrador sin fotografías no acredita la apariencia final ni el rendimiento público. Los objetivos LCP, CLS, INP y PageSpeed requieren medición real después de publicar las imágenes.

Los scripts históricos de diagnóstico SSH se conservan como referencia; el acceso operativo es cPanel HTTPS y no requiere probar más puertos ni nuevas credenciales.
