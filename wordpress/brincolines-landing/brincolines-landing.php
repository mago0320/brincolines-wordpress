<?php
/**
 * Plugin Name: Brincolines Jumping · Landing
 * Description: Estilos y SEO de la portada Gutenberg, conservando Kadence.
 * Version: 1.0.0
 */
defined('ABSPATH') || exit;

function bj_landing_enabled() {
    return (is_front_page() || is_preview()) && get_post_meta(get_queried_object_id(), '_bj_landing', true) === '1';
}
// Kadence's layout filter suppresses its extra H1 and chrome in HTML.
add_filter('kadence_post_layout', function ($layout) {
    if (!bj_landing_enabled()) return $layout;
    return array_merge($layout, ['title'=>'disable','header'=>'disable','footer'=>'disable',
        'layout'=>'fullwidth','sidebar'=>'disable','boxed'=>'unboxed','vpadding'=>'disable','feature'=>'hide','comments'=>'hide']);
});
add_filter('body_class', function ($classes) {
    if (bj_landing_enabled()) $classes[] = 'bj-landing-active';
    return $classes;
});
add_action('wp_enqueue_scripts', function () {
    if (!bj_landing_enabled()) return;
    wp_enqueue_style('bj-landing', plugins_url('landing.css', __FILE__), [], filemtime(__DIR__.'/landing.css'));
});
add_filter('document_title_parts', function ($parts) {
    if (bj_landing_enabled()) return ['title'=>'Renta de brincolines en Aguascalientes | Brincolines Jumping'];
    return $parts;
});
add_filter('render_block_core/image', function ($html, $block) {
    if (!bj_landing_enabled() || !class_exists('WP_HTML_Tag_Processor')) return $html;
    $id = (int)($block['attrs']['id'] ?? 0);
    $hero = strpos($block['attrs']['className'] ?? '', 'bj-hero-photo') !== false;
    $processor = new WP_HTML_Tag_Processor($html);
    if ($processor->next_tag('IMG')) {
        $processor->set_attribute('loading', $hero ? 'eager' : 'lazy');
        $processor->set_attribute('decoding', 'async');
        if ($hero) $processor->set_attribute('fetchpriority', 'high');
        if ($id) {
            $metadata = wp_get_attachment_metadata($id);
            if ($metadata && !empty($metadata['width']) && !empty($metadata['height'])) {
                $processor->set_attribute('width', (string)$metadata['width']);
                $processor->set_attribute('height', (string)$metadata['height']);
            }
        }
    }
    return $processor->get_updated_html();
}, 10, 2);
add_action('wp_head', function () {
    if (!bj_landing_enabled()) return;
    $description='Renta de brincolines en Aguascalientes. Conoce nuestros modelos reales para cumpleaños y fiestas infantiles. Consulta disponibilidad y cotiza por WhatsApp.';
    $image=wp_get_attachment_image_url(get_post_thumbnail_id(get_queried_object_id()), 'large');
    $tags=['description'=>$description,'og:title'=>'¡La diversión llega a tu fiesta! · Brincolines Jumping','og:description'=>$description,'og:type'=>'website','og:url'=>home_url('/'),'og:site_name'=>'Brincolines Jumping','og:locale'=>'es_MX','twitter:card'=>'summary_large_image'];
    if ($image) $tags['og:image']=$image;
    foreach ($tags as $key=>$value) echo '<meta '.(strpos($key,'og:')===0?'property':'name').'="'.esc_attr($key).'" content="'.esc_attr($value).'">'."\n";
    $business=['@type'=>'LocalBusiness','@id'=>home_url('/#negocio'),'name'=>'Brincolines Jumping','url'=>home_url('/'),'telephone'=>'+524491911663','areaServed'=>['@type'=>'City','name'=>'Aguascalientes']];
    if ($image) $business['image']=$image;
    $service=['@type'=>'Service','name'=>'Renta de brincolines en Aguascalientes','serviceType'=>'Renta de brincolines para cumpleaños y fiestas infantiles','provider'=>['@id'=>home_url('/#negocio')],'areaServed'=>['@type'=>'City','name'=>'Aguascalientes']];
    echo '<script type="application/ld+json">'.wp_json_encode(['@context'=>'https://schema.org','@graph'=>[$business,$service]],JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_HEX_TAG).'</script>'."\n";
}, 5);
// Replace only the obsolete demo contact URL; the landing contains all contact details.
add_action('template_redirect', function () {
    $front=(int)get_option('page_on_front');
    if (get_post_meta($front,'_bj_landing',true)!=='1') return;
    $path=untrailingslashit(wp_parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH));
    if ($path==='/contact-us') {
        wp_safe_redirect(home_url('/#contacto'),301);
        exit;
    }
});
