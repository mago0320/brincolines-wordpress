# Brincolines Jumping · WordPress existente

El sitio de producción es **https://brincolinesjumping.com/**. Conserva **Kadence** y la portada estática ID **42**, ahora publicada con bloques Gutenberg, ocho fotografías reales y el botón flotante **Contratar ahora**. La auditoría inicial encontró una plantilla de demostración con metadatos Elementor; la portada ya utiliza la plantilla predeterminada de Kadence. El complemento pequeño de la landing permanece limitado a portada/vista previa marcada. Este repositorio no instala WordPress ni crea otro tema.

## Acceso verificado sin SSH externo

Desde Cloud funciona el inicio de sesión HTTPS de cPanel y su Terminal por WebSocket, con certificados verificados. WP-CLI ejecutado por esa Terminal confirmó `home` y `siteurl` del dominio autorizado y descartó multisite. El puerto SSH externo sigue rechazando la conexión; no es necesario seguir probando puertos.

`scripts/cpanel-wordpress.py` reproduce el inventario de forma autónoma. Comprueba primero el documentroot de este dominio y los archivos WordPress; después revalida las URL desde WP-CLI antes de leer opciones. Omite el arranque de plugins y temas durante la consulta. Sus informes no contienen rutas de cuenta, contraseñas ni cookies. La sesión y sus credenciales permanecen en memoria.

El workflow manual **BanaHosting - WordPress por cPanel HTTPS** usa esta vía y no prueba ningún puerto SSH. Reutiliza el usuario guardado en los secrets existentes y `BANAHOST_CPANEL_PASSWORD` (también admite `BANAHOST_PASSWORD` o `CPANEL_PASSWORD`). El acceso real desde Actions quedó verificado en la [ejecución 37680310022](https://github.com/mago0320/brincolines-wordpress/actions/runs/37680310022): inicio de sesión, dominio, archivos WordPress y WP-CLI correctos, Kadence activo y sin multisite. El workflow actual solo inventaría, sin desplegar ni modificar producción.

El cliente sigue el flujo de inicio de sesión del navegador, conservando la cookie previa solo en memoria. Elimina únicamente saltos de línea CR/LF finales que puedan añadirse al pegar la contraseña; conserva espacios y rechaza saltos de línea internos antes de autenticar. El diagnóstico identifica la etapa y señales conocidas del rechazo sin publicar el cuerpo de errores, credenciales ni cookies. Las 26 pruebas de cPanel pasaron tanto localmente como en la ejecución verificada de Actions.

La [publicación 37701334398](https://github.com/mago0320/brincolines-wordpress/actions/runs/37701334398), con código `5fbb6d635e8b137e7d567e3aecb4d84e202b1527`, terminó correctamente: respaldo privado `20261007T231657Z-3768fb64c520`, portada **42** publicada y ocho fotos importadas/reutilizadas (adjuntos 84–91), sin pendientes. También pasaron las comprobaciones del navegador contra la URL real. El borrador **81** se conserva privado como historial; no debe convertirse en portada. **Contact Us (13)** se retiró a borrador y `/contact-us/` redirige a `/#contacto`.

## Landing móvil con Kadence y Gutenberg

El WhatsApp confirmado por el propietario es **449 191 1663** (`524491911663`). El catálogo de ocho modelos está en `content/catalog.json`. No se utilizan las tarifas, teléfonos antiguos ni testimonios del mockup.

`assets/catalog/` contiene los ocho productos reales con fondo transparente, en WebP: 444,226 bytes en total. Se eliminaron fondos y anuncios externos con máscaras, conservando los píxeles RGB de cada producto; la comparación antes del recorte dio cero diferencias. `provenance.json` registra dimensiones y hashes de los originales y archivos preparados. Los rótulos impresos físicamente en los inflables conservan su aspecto original; todos los enlaces y datos de contacto de la web usan el teléfono nuevo. El botón flotante dice **Contratar ahora** y abre WhatsApp.

`wordpress/brincolines-landing/` contiene un complemento pequeño de CSS y SEO aislado. Conserva Kadence y usa bloques nativos editables: grupos, títulos, párrafos, imágenes, botones y acordeones. No incorpora otro constructor, fuentes remotas ni JavaScript propio.

Para esta portada marcada, el complemento evita los contenedores de grupo heredados que WordPress agrega a temas clásicos y carga sus estilos después de Kadence. Esto conserva las filas del encabezado y las cuadrículas responsive, sin modificar el tema. El despliegue establece permisos 755 en el directorio del complemento propio y 644 en sus archivos públicos; staging y respaldos permanecen privados con 700/600.

El workflow **Brincolines Jumping - Landing manual** se ejecuta únicamente con `workflow_dispatch`. Reutiliza los mismos secrets y transporte HTTPS verificado del inventario anterior. Valida PHP, bloques y restricciones antes de aplicar una operación. Revalida dominio, documentroot, ausencia de multisite, Kadence y portada ID 42.

| Operación | Efecto |
| --- | --- |
| `backup` | Copia privada recuperable de las páginas afectadas, metadatos, opciones y archivos del complemento. |
| `draft` | Crea o actualiza una página borrador editable; conserva la portada pública. Las fotos pendientes están rotuladas únicamente en este borrador. |
| `publish` | Importa fotografías reales disponibles, crea variantes en Media Library, reemplaza la portada 42 y retira la página Contact Us de demostración con redirección a `/#contacto`. Requiere la fotografía real principal. |
| `styles` | Respalda y actualiza únicamente el CSS del complemento propio, conservando las páginas, fotos, opciones y PHP. Su rollback también conserva las páginas. |
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

La publicación final se comprobó a 375, 390, 430, 768 y 1440 px: sin desbordamientos, H1 único, enlaces al teléfono confirmado, botones táctiles, acordeones con teclado, cuadrículas correctas y CTA flotante sin tapar el CTA principal en la primera pantalla móvil. Cada fotografía se visita y decodifica para comprobar su carga lazy. HTTPS, portada HTTP 200, WebP con hashes coincidentes, dimensiones/srcset/alt, canonical, Open Graph, datos estructurados, robots y sitemap se verificaron en la URL real; la página de demostración ya no figura en el sitemap.

Chrome en Actions midió **LCP de laboratorio entre 444 y 816 ms y CLS 0** en esos cinco tamaños, sin limitar red/CPU y antes del scroll. No se midió INP de usuarios reales ni un puntaje PageSpeed. Las capturas de borrador y el puente visual local no acreditan rendimiento público.

`scripts/check-landing-visual.py` guarda las capturas y comprueba estos criterios y la posición del botón flotante en Chromium/Chrome. El workflow lo ejecuta contra la URL real tras `publish` y registra LCP/CLS de laboratorio en Chrome sin limitar CPU/red, antes de desplazar la página. Estas muestras no acreditan INP de usuarios reales ni un puntaje PageSpeed. Para verificaciones locales con navegador se utilizan las dependencias de `requirements-visual.txt`; la opción `--draft-file` identifica explícitamente una vista preliminar y `--tls-bridge` permite comprobaciones visuales mediante HTTP con certificado verificado si Chromium no reconoce la CA del proxy. Esa ruta no mide rendimiento público.

Los scripts históricos de diagnóstico SSH se conservan como referencia; el acceso operativo es cPanel HTTPS y no requiere probar más puertos ni nuevas credenciales.
