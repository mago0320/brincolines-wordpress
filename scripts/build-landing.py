#!/usr/bin/env python3
"""Generate editable native WordPress blocks. Production requires a real hero."""
import argparse
import html
import json
from pathlib import Path
import re
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


def block(name, markup, attrs=None):
    attributes = ' ' + json.dumps(attrs, ensure_ascii=False, separators=(',', ':')) if attrs else ''
    return f'<!-- wp:{name}{attributes} -->\n{markup}\n<!-- /wp:{name} -->\n'


def group(children, classes='', anchor=None, tag='div'):
    attrs = {'className': classes}
    if anchor:
        attrs['anchor'] = anchor
    if tag != 'div':
        attrs['tagName'] = tag
    element_id = f' id="{anchor}"' if anchor else ''
    return block('group', f'<{tag}{element_id} class="wp-block-group {classes}">{children}</{tag}>', attrs)


def heading(text, level=2):
    return block('heading', f'<h{level} class="wp-block-heading">{text}</h{level}>', {'level': level})


def paragraph(text, classes=''):
    attribute = f' class="{classes}"' if classes else ''
    return block('paragraph', f'<p{attribute}>{text}</p>', {'className': classes} if classes else None)


def details(summary, text, classes=''):
    return block('details', f'<details class="wp-block-details {classes}"><summary>{summary}</summary>{paragraph(text)}</details>', {'className': classes})


def whatsapp(config, message):
    if not re.fullmatch(r'52\d{10}', config['whatsapp']):
        raise ValueError('Invalid verified WhatsApp')
    return 'https://wa.me/' + config['whatsapp'] + '?text=' + urllib.parse.quote(message, safe='')


def buttons(url, label='Cotiza por WhatsApp', classes=''):
    button = block('button', '<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="' + html.escape(url, quote=True) + '">' + label + '</a></div>')
    return block('buttons', f'<div class="wp-block-buttons {classes}">{button}</div>', {'className': classes} if classes else None)


def validate_manifest(config, manifest, draft=False):
    if not isinstance(manifest, dict):
        raise ValueError('Invalid photo manifest')
    missing = []
    for model in config['models']:
        photo = manifest.get(model['slug'])
        if photo is None:
            missing.append(model['slug'])
            continue
        url = urllib.parse.urlsplit(photo.get('url', ''))
        if url.scheme != 'https' or url.hostname not in {'brincolinesjumping.com', 'www.brincolinesjumping.com'} or url.username or url.password:
            raise ValueError('Photo URL outside authorized HTTPS domain')
        if not url.path.startswith('/wp-content/uploads/') or '..' in url.path.split('/'):
            raise ValueError('Photo outside Media Library')
        for key in ('id', 'width', 'height'):
            if not isinstance(photo.get(key), int) or isinstance(photo[key], bool) or photo[key] <= 0:
                raise ValueError('Invalid attachment metadata')
    if config['hero'] in missing and not draft:
        raise ValueError('Original hero photo file required')
    return missing


def build(config, manifest, draft=False):
    missing = validate_manifest(config, manifest, draft)
    models = {model['slug']: model for model in config['models']}
    general = whatsapp(config, 'Hola, quiero cotizar un brincolín para mi fiesta en Aguascalientes. ¿Me compartes disponibilidad y precio?')

    def photo(slug, classes=''):
        model = models[slug]
        if slug not in manifest:
            # Private draft only. Never passed by the production publication guard.
            return group(paragraph('Foto original pendiente<br><strong>' + html.escape(model['name']) + '</strong>'), 'bj-pending-photo ' + classes)
        item = manifest[slug]
        markup = f'<figure class="wp-block-image size-large {classes}"><img src="{html.escape(item["url"], quote=True)}" alt="{html.escape(model["alt"], quote=True)}" class="wp-image-{item["id"]}"/></figure>'
        return block('image', markup, {'id': item['id'], 'sizeSlug': 'large', 'linkDestination': 'none', 'className': classes})

    def section_title(title, subtitle=''):
        return group(heading(title) + (paragraph(subtitle) if subtitle else ''), 'bj-section-heading')

    header = group(paragraph('<a href="#inicio">Brincolines<br><strong>JUMPING</strong></a>', 'bj-brand') + buttons(general, '¡Cotiza ahora!') + details('Menú', '<a href="#brincolines">Brincolines</a><a href="#como-cotizar">Cómo cotizar</a><a href="#preguntas">Preguntas</a><a href="#contacto">Contacto</a>', 'bj-menu'), 'bj-header bj-wrap', tag='header')
    hero_copy = group(paragraph('Fiestas en Aguascalientes', 'bj-eyebrow') + heading('¡La diversión<br><strong>llega a tu fiesta!</strong>', 1) + paragraph('Renta de brincolines en Aguascalientes para cumpleaños, fiestas infantiles y celebraciones.', 'bj-lead') + buttons(general) + group(paragraph('Modelos reales') + paragraph('Cotiza por WhatsApp') + paragraph('Elige tu favorito'), 'bj-pills'), 'bj-hero-copy')
    hero = group(group(hero_copy + photo(config['hero'], 'bj-hero-photo'), 'bj-wrap bj-hero-grid'), 'bj-hero', 'inicio', 'section')
    cards = ''
    for model in config['models']:
        slug = model['slug']
        if not draft and slug not in manifest:
            continue
        message = 'Hola, quiero cotizar la renta del brincolín ' + model['name'] + ' en Aguascalientes. ¿Me compartes disponibilidad y precio?'
        copy = paragraph(html.escape(model['category']), 'bj-category') + heading(html.escape(model['name']), 3) + paragraph(html.escape(model['description'])) + buttons(whatsapp(config, message), 'Cotizar este modelo')
        cards += group(photo(slug) + group(copy, 'bj-card-copy'), 'bj-card')
    catalog = group(section_title('Nuestros Brincolines', 'Modelos reales. Encuentra el que va con tu fiesta.') + group(cards, 'bj-catalog'), 'bj-wrap bj-section', 'brincolines', 'section')
    options = group(group(heading('Elige tu opción') + paragraph('¿Temático, con resbaladilla o interactivo? Cuéntanos qué modelo te gusta, la fecha y la ubicación de tu evento. Te compartimos disponibilidad y cotización.'), 'bj-options-copy') + buttons(general, 'Ayúdame a elegir'), 'bj-options')
    options = group(options, 'bj-wrap bj-section', 'opciones', 'section')
    benefits = ''
    for icon, title, text in [('✦', 'Conoce lo que rentas', 'Mira los modelos reales antes de elegir tu favorito.'), ('↗', 'Contacto directo', 'Cotiza con nosotros por WhatsApp, sin formularios largos.'), ('♡', 'Una fiesta a tu medida', 'Comparte tu fecha y espacio para consultar las opciones.')]:
        benefits += group(paragraph(icon, 'bj-icon') + heading(title, 3) + paragraph(text), 'bj-benefit')
    benefits = group(section_title('¿Por qué elegirnos?') + group(benefits, 'bj-benefits'), 'bj-wrap bj-section', 'por-que-elegirnos', 'section')
    conversion_slug='frozen' if draft or 'frozen' in manifest else config['hero']
    conversion = group(photo(conversion_slug) + group(heading('Haz de tu fiesta un momento inolvidable.') + paragraph('Elige tu brincolín y empieza a planear la diversión.') + buttons(general), 'bj-conversion-copy'), 'bj-conversion')
    conversion = group(conversion, 'bj-wrap bj-section', tag='section')
    gallery_slugs=[slug for slug in ['paw-patrol','toy-story','rampa-verde','barco-escalador'] if draft or slug in manifest]
    if not gallery_slugs:
        gallery_slugs=list(manifest)[:4]
    gallery = group(section_title('Diversión en todos los colores', 'Dale otra mirada a nuestros brincolines.') + group(''.join(photo(slug) for slug in gallery_slugs), 'bj-gallery'), 'bj-wrap bj-section', 'galeria', 'section')
    steps = ''
    for number, title, text in [('01', 'Elige un modelo', 'Busca tu favorito en nuestro catálogo.'), ('02', 'Cuéntanos tu evento', 'Envíanos fecha, zona y espacio disponible por WhatsApp.'), ('03', 'Consulta y reserva', 'Confirma disponibilidad, precio y condiciones antes de reservar.')]:
        steps += group(paragraph(number, 'bj-icon') + heading(title, 3) + paragraph(text), 'bj-step')
    steps = group(section_title('Así de fácil cotizar') + group(steps, 'bj-steps'), 'bj-wrap bj-section', 'como-cotizar', 'section')
    faq_items = [
        ('¿Cómo consulto disponibilidad y precio?', 'Envíanos por WhatsApp el modelo que te interesa, la fecha de tu evento y la ubicación en Aguascalientes. Te compartimos la cotización.'),
        ('¿Cuánto tiempo dura la renta?', 'Consulta la duración disponible al cotizar tu modelo y fecha. Confirma el horario antes de reservar.'),
        ('¿La instalación está incluida?', 'Pide que la cotización detalle entrega, instalación y retiro, además de sus condiciones y costo, antes de confirmar.'),
        ('¿En qué zonas tienen servicio?', 'Atendemos consultas para eventos en Aguascalientes. Envíanos tu ubicación para confirmar la cobertura y el traslado.'),
        ('¿Qué espacio necesito?', 'Comparte las medidas del lugar y el modelo que te gusta. Consulta sus dimensiones y los requisitos de instalación antes de reservar.'),
        ('¿Cómo reservo mi brincolín?', 'Escríbenos para consultar disponibilidad. Confirma directamente con nosotros las condiciones de reserva para tu fecha.'),
        ('¿Qué sucede si hay lluvia o viento?', 'Consulta las condiciones de uso y la política aplicable al clima antes de reservar; confirma con nosotros lo que corresponde a tu evento.')
    ]
    faq = group(section_title('Preguntas frecuentes') + group(''.join(details(q, a) for q, a in faq_items), 'bj-faq'), 'bj-wrap bj-section', 'preguntas', 'section')
    contact = group(heading('¡Cotizamos tu fiesta!') + paragraph('Brincolines en renta en Aguascalientes.<br>Escríbenos y cuéntanos qué tienes en mente.') + paragraph('<a href="' + html.escape(general, quote=True) + '">' + html.escape(config['display_phone']) + '</a>', 'bj-phone') + buttons(general), 'bj-contact')
    contact = group(contact, 'bj-wrap bj-section', 'contacto', 'section')
    privacy = details('Sobre tu contacto por WhatsApp', 'Al pulsar “Cotizar” abrirás WhatsApp. Brincolines Jumping utilizará la información que compartas en la conversación para atender tu consulta sobre disponibilidad y cotización. Puedes solicitar aclaraciones sobre tus datos en ese mismo número. El uso de WhatsApp se rige también por <a href="https://www.whatsapp.com/legal/privacy-policy">su política de privacidad</a>.', 'bj-privacy')
    footer = group(paragraph('<strong>Brincolines Jumping</strong><br>Diversión para tu fiesta en Aguascalientes.<br>© 2026 Brincolines Jumping.') + paragraph('<a href="#brincolines">Brincolines</a><a href="#preguntas">Preguntas</a><a href="#contacto">Contacto</a>', 'bj-footer-links') + privacy, 'bj-wrap bj-footer', tag='footer')
    floating = buttons(general, 'Contratar ahora', 'bj-floating')
    return group(header + hero + catalog + options + benefits + conversion + gallery + steps + faq + contact + footer + floating, 'bj-landing'), missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--draft', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / '.local/landing/blocks.html')
    args = parser.parse_args()
    config = json.loads((ROOT / 'content/catalog.json').read_text())
    manifest = json.loads(args.manifest.read_text()) if args.manifest else {}
    content, missing = build(config, manifest, args.draft)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    print(json.dumps({'native_blocks_generated': True, 'publication_ready': config['hero'] not in missing, 'models': len(config['models']), 'missing_original_photos': missing}))


if __name__ == '__main__':
    main()
