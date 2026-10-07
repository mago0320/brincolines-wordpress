<?php
// Executed by WP-CLI after the Python transport verifies the site's documentroot.
if (!defined('ABSPATH') || is_multisite() || !in_array(untrailingslashit(home_url()), ['https://brincolinesjumping.com','https://www.brincolinesjumping.com'], true)) {
    throw new RuntimeException('landing_domain_guard_failed');
}
$options = [];
foreach (['blogname','blogdescription','blog_public','show_on_front','page_on_front','page_for_posts','page_for_privacy_policy','permalink_structure','timezone_string','template','stylesheet','active_plugins','theme_mods_kadence'] as $name) {
    $options[$name] = get_option($name);
}
$pages = [];
foreach (get_posts(['post_type'=>'page','post_status'=>['publish','draft','private'],'numberposts'=>100]) as $post) {
    $pages[] = ['id'=>$post->ID,'title'=>$post->post_title,'status'=>$post->post_status,'slug'=>$post->post_name,'content'=>$post->post_content,'meta'=>get_post_meta($post->ID)];
}
$media = [];
foreach (get_posts(['post_type'=>'attachment','post_status'=>'inherit','numberposts'=>500]) as $post) {
    $media[] = ['id'=>$post->ID,'title'=>$post->post_title,'url'=>wp_get_attachment_url($post->ID),'alt'=>get_post_meta($post->ID,'_wp_attachment_image_alt',true),'metadata'=>wp_get_attachment_metadata($post->ID)];
}
$upload = wp_upload_dir();
$unregistered = [];
$base = realpath($upload['basedir']);
if ($base) {
    $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($base, FilesystemIterator::SKIP_DOTS));
    foreach ($iterator as $file) {
        if (!$file->isFile() || $file->isLink()) continue;
        $real = $file->getRealPath();
        if (strpos($real, $base.DIRECTORY_SEPARATOR)!==0) continue;
        if (!preg_match('/\.(?:jpe?g|png|webp|avif)$/i',$file->getFilename()) || preg_match('/-\d+x\d+\./',$file->getFilename())) continue;
        $unregistered[] = ['file'=>substr($real,strlen($base)+1),'bytes'=>$file->getSize()];
        if (count($unregistered)>=500) break;
    }
}
require_once ABSPATH.'wp-admin/includes/plugin.php';
$plugins = [];
foreach (get_plugins() as $file=>$data) $plugins[]=['file'=>$file,'name'=>$data['Name'],'version'=>$data['Version'],'active'=>is_plugin_active($file)];
$themes = [];
foreach (wp_get_themes() as $slug=>$theme) $themes[]=['slug'=>$slug,'version'=>$theme->get('Version')];
echo wp_json_encode(['home'=>home_url(),'options'=>$options,'pages'=>$pages,'media'=>$media,'upload_images'=>$unregistered,'plugins'=>$plugins,'themes'=>$themes,'php_version'=>PHP_VERSION,'wp_version'=>get_bloginfo('version'),'additional_css'=>wp_get_custom_css()]);
