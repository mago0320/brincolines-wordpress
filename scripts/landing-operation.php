<?php
/* Run exclusively via WP-CLI with a private JSON payload and a verified site. */
defined('ABSPATH') || exit;

function bj_operation_require($condition, $reason) {
    if (!$condition) throw new RuntimeException($reason);
}
function bj_operation_write($path, $bytes, $mode=0600) {
    bj_operation_require(!is_link($path), 'symlink_rejected');
    $temporary=$path.'.'.bin2hex(random_bytes(5)).'.tmp';
    bj_operation_require(file_put_contents($temporary,$bytes,LOCK_EX)===strlen($bytes), 'file_write_failed');
    chmod($temporary,$mode);
    bj_operation_require(rename($temporary,$path), 'file_commit_failed');
}
function bj_operation_snapshot($post_ids, $plugin_dir) {
    $snapshot=['domain'=>'brincolinesjumping.com','version'=>1,'posts'=>[], 'options'=>[], 'plugin_files'=>[]];
    foreach (array_unique($post_ids) as $id) {
        if (!$id || !get_post($id)) continue;
        $snapshot['posts'][$id]=['post'=>get_post($id,ARRAY_A),'meta'=>get_post_meta($id)];
    }
    foreach (['blogname','blogdescription','WPLANG','show_on_front','page_on_front','active_plugins','bj_landing_draft_id'] as $key) {
        $sentinel='BJ_OPTION_ABSENT_82ade03c';
        $value=get_option($key,$sentinel);
        $snapshot['options'][$key]=['exists'=>$value!==$sentinel,'value'=>$value===$sentinel?null:$value];
    }
    foreach (['brincolines-landing.php','landing.css'] as $file) {
        $path=$plugin_dir.'/'.$file;
        bj_operation_require(!is_link($path),'plugin_symlink_rejected');
        $snapshot['plugin_files'][$file]=is_file($path)?base64_encode(file_get_contents($path)):null;
    }
    return $snapshot;
}
function bj_operation_backup($snapshot, $base, $release) {
    $directory=$base.'/'.$release;
    bj_operation_require(!file_exists($directory) && !is_link($directory),'backup_collision');
    bj_operation_require(mkdir($directory,0700),'backup_directory_failed');
    $json=wp_json_encode($snapshot,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
    bj_operation_write($directory.'/before.json',$json);
    bj_operation_require(hash_file('sha256',$directory.'/before.json')===hash('sha256',$json),'backup_verification_failed');
    bj_operation_write($directory.'/before.sha256',hash('sha256',$json));
    return $directory;
}
function bj_operation_validate_blocks($content, $require_photos) {
    bj_operation_require(is_string($content) && strlen($content)<200000,'content_limit');
    $allowed=['core/group','core/paragraph','core/heading','core/image','core/button','core/buttons','core/details'];
    $walk=function($blocks) use (&$walk,$allowed) {
        foreach($blocks as $block) {
            if ($block['blockName']===null && trim($block['innerHTML'])==='') continue;
            bj_operation_require(in_array($block['blockName'],$allowed,true),'unsupported_or_uneditable_block');
            $walk($block['innerBlocks']);
        }
    };
    $walk(parse_blocks($content));
    bj_operation_require(preg_match_all('/<h1(?:\s|>)/',$content)===1,'single_h1_required');
    preg_match_all('#href="(https://wa\.me/[^\"]+)"#',$content,$links);
    bj_operation_require(count($links[1])>=7,'whatsapp_ctas_missing');
    foreach($links[1] as $link) bj_operation_require(strpos(html_entity_decode($link),'https://wa.me/524491911663?text=')===0,'whatsapp_not_verified');
    if ($require_photos) {
        bj_operation_require(strpos($content,'bj-pending-photo')===false,'original_photos_missing');
        bj_operation_require(preg_match_all('/<!-- wp:image /',$content)>=1,'real_catalog_images_missing');
    }
}

try {
    $payload_path=getenv('BJ_PAYLOAD_PATH');
    bj_operation_require(is_string($payload_path) && is_file($payload_path) && !is_link($payload_path),'payload_missing');
    $payload=json_decode(file_get_contents($payload_path),true,512,JSON_THROW_ON_ERROR);
    $operation=$payload['operation'] ?? '';
    bj_operation_require(in_array($operation,['backup','draft','import','publish','styles','rollback'],true),'operation_rejected');
    bj_operation_require(!is_multisite(),'multisite_rejected');
    foreach(['home','siteurl'] as $key) bj_operation_require(in_array(untrailingslashit(get_option($key)),['https://brincolinesjumping.com','https://www.brincolinesjumping.com'],true),'domain_mismatch');
    bj_operation_require(realpath(ABSPATH)===realpath($payload['verified_root'] ?? ''),'root_mismatch');
    bj_operation_require(get_option('stylesheet')==='kadence' && get_option('template')==='kadence','existing_theme_changed');
    $front=(int)get_option('page_on_front');
    bj_operation_require($front===42 && get_post_type($front)==='page','front_page_changed');
    $home=getenv('HOME');
    bj_operation_require(is_string($home) && $home[0]==='/' && realpath($home)!==false,'home_not_verified');
    $backup_base=$home.'/.brincolinesjumping-backups';
    bj_operation_require(!is_link($backup_base),'backup_base_symlink');
    if (!is_dir($backup_base)) bj_operation_require(mkdir($backup_base,0700),'backup_base_failed');
    bj_operation_require(realpath($backup_base)===realpath($home).'/.brincolinesjumping-backups','backup_base_scope');
    $plugin_dir=WP_PLUGIN_DIR.'/brincolines-landing';
    bj_operation_require(!is_link($plugin_dir),'plugin_directory_symlink');
    $plugin='brincolines-landing/brincolines-landing.php';
    require_once ABSPATH.'wp-admin/includes/plugin.php';
    require_once ABSPATH.'wp-admin/includes/file.php';
    require_once ABSPATH.'wp-admin/includes/media.php';
    require_once ABSPATH.'wp-admin/includes/image.php';

    if ($operation==='rollback') {
        $id=$payload['backup_id'] ?? '';
        bj_operation_require(preg_match('/^\d{8}T\d{6}Z-[a-f0-9]{12}$/',$id),'invalid_backup_id');
        $dir=$backup_base.'/'.$id;
        bj_operation_require(!is_link($dir) && realpath($dir)===realpath($backup_base).'/'.$id,'backup_scope');
        bj_operation_require(hash_file('sha256',$dir.'/before.json')===trim(file_get_contents($dir.'/before.sha256')),'backup_checksum_mismatch');
        $before=json_decode(file_get_contents($dir.'/before.json'),true,512,JSON_THROW_ON_ERROR);
        $after=json_decode(file_get_contents($dir.'/after.json'),true,512,JSON_THROW_ON_ERROR);
        bj_operation_require(($before['domain'] ?? '')==='brincolinesjumping.com','backup_domain_mismatch');
        // Refuse to overwrite any content, options or files edited since this release.
        foreach($after['posts'] as $post_id=>$value) {
            bj_operation_require(hash('sha256',get_post_field('post_content',$post_id))===$value['content_sha256'],'later_page_edit_detected');
            bj_operation_require(get_post_status($post_id)===$value['status'],'later_page_status_detected');
            bj_operation_require(get_post_field('post_title',$post_id)===$value['title'],'later_title_edit_detected');
            foreach($value['managed_meta'] as $key=>$values) bj_operation_require(get_post_meta($post_id,$key)===$values,'later_page_meta_edit_detected');
        }
        foreach($after['options'] as $key=>$value) bj_operation_require(get_option($key,null)===$value,'later_option_edit_detected');
        foreach($after['plugin_files'] as $file=>$hash) bj_operation_require(hash_file('sha256',$plugin_dir.'/'.$file)===$hash,'later_plugin_edit_detected');
        $undo_id=gmdate('Ymd\THis\Z').'-'.bin2hex(random_bytes(6));
        bj_operation_backup(bj_operation_snapshot(array_keys($after['posts']),$plugin_dir),$backup_base,$undo_id);
        deactivate_plugins($plugin,true);
        foreach($before['plugin_files'] as $file=>$bytes) if ($bytes!==null) bj_operation_write($plugin_dir.'/'.$file,base64_decode($bytes,true),0644);
        foreach($before['posts'] as $post_id=>$snapshot) {
            $fields=array_intersect_key($snapshot['post'],array_flip(['ID','post_author','post_date','post_date_gmt','post_content','post_title','post_excerpt','post_status','comment_status','ping_status','post_password','post_name','post_modified','post_modified_gmt','post_parent','menu_order','post_type','post_mime_type']));
            $result=wp_update_post(wp_slash($fields),true);
            bj_operation_require(!is_wp_error($result),'restore_post_failed');
            foreach(['_bj_landing','_wp_page_template','_elementor_data','_elementor_edit_mode','_elementor_template_type','_elementor_controls_usage','_thumbnail_id'] as $key) {
                delete_post_meta($post_id,$key);
                foreach($snapshot['meta'][$key] ?? [] as $value) add_post_meta($post_id,$key,wp_slash(maybe_unserialize($value)));
            }
        }
        foreach($after['posts'] as $post_id=>$value) if (!isset($before['posts'][$post_id])) {
            wp_update_post(['ID'=>$post_id,'post_status'=>'draft']);
            delete_post_meta($post_id,'_bj_landing');
        }
        foreach($before['options'] as $key=>$entry) {
            if ($entry['exists']) update_option($key,$entry['value']); else delete_option($key);
        }
        // Added media/files remain, avoiding deletion of existing files.
        wp_cache_flush();
        echo wp_json_encode(['ok'=>true,'operation'=>'rollback','backup_id'=>$id,'undo_backup_id'=>$undo_id,'domain'=>'brincolinesjumping.com']);
        return;
    }

    $release=$payload['release'];
    bj_operation_require(preg_match('/^\d{8}T\d{6}Z-[a-f0-9]{12}$/',$release),'invalid_release');
    if ($operation==='styles') {
        bj_operation_require(is_plugin_active($plugin) && get_post_meta($front,'_bj_landing',true)==='1','landing_styles_not_ready');
        bj_operation_require(realpath($plugin_dir)===realpath(WP_PLUGIN_DIR).'/brincolines-landing','plugin_directory_scope');
        bj_operation_require(strpos(file_get_contents($plugin_dir.'/brincolines-landing.php'),'Brincolines Jumping · Landing')!==false,'existing_plugin_not_owned');
        $css=$payload['css'] ?? '';
        bj_operation_require(is_string($css) && strlen($css)>100 && strlen($css)<50000 && strpos($css,'.bj-landing')!==false,'landing_css_rejected');
        $page_before=get_post($front,ARRAY_A);
        // A style rollback must not restore pages, unrelated options or PHP.
        $before=bj_operation_snapshot([],$plugin_dir);
        $before['options']=array_intersect_key($before['options'],['active_plugins'=>true]);
        $before['plugin_files']=array_intersect_key($before['plugin_files'],['landing.css'=>true]);
        $backup_dir=bj_operation_backup($before,$backup_base,$release);
        bj_operation_write($plugin_dir.'/landing.css',$css,0644);
        $after=['posts'=>[],'options'=>['active_plugins'=>get_option('active_plugins')],'plugin_files'=>['landing.css'=>hash_file('sha256',$plugin_dir.'/landing.css')]];
        bj_operation_write($backup_dir.'/after.json',wp_json_encode($after));
        echo wp_json_encode(['ok'=>true,'operation'=>'styles','backup_id'=>$release,'page_id'=>$front,'page_unchanged'=>$page_before===get_post($front,ARRAY_A),'css_sha256'=>$after['plugin_files']['landing.css'],'domain'=>'brincolinesjumping.com']);
        return;
    }
    $draft=(int)get_option('bj_landing_draft_id');
    if ($draft) bj_operation_require(get_post_type($draft)==='page' && get_post_meta($draft,'_bj_preview',true)==='1' && get_post_status($draft)==='draft','draft_page_changed');
    $before=bj_operation_snapshot([$front,13,$draft],$plugin_dir);
    $backup_dir=bj_operation_backup($before,$backup_base,$release);
    if ($operation==='backup') {
        echo wp_json_encode(['ok'=>true,'operation'=>'backup','backup_id'=>$release,'checksum'=>hash_file('sha256',$backup_dir.'/before.json'),'domain'=>'brincolinesjumping.com']);
        return;
    }

    if ($operation==='import') {
        $expected=['mickey-minnie','rampa-verde','clasico-resbaladilla','frozen','angry-birds','barco-escalador','toy-story','paw-patrol','unicornio','logo'];
        $photos=$payload['photos'] ?? [];
        bj_operation_require(isset($photos['mickey-minnie']) && !array_diff(array_keys($photos),$expected),'real_hero_photo_required');
        $upload=wp_upload_dir();
        bj_operation_require(empty($upload['error']) && strpos(realpath($upload['basedir']),realpath(WP_CONTENT_DIR).DIRECTORY_SEPARATOR)===0,'uploads_directory_scope');
        $manifest=[];
        foreach(array_keys($photos) as $slug) {
            $item=$photos[$slug];
            $bytes=base64_decode($item['bytes'] ?? '',true);
            bj_operation_require($bytes!==false && strlen($bytes)>100 && strlen($bytes)<1500000,'photo_size_rejected');
            bj_operation_require(hash('sha256',$bytes)===($item['sha256'] ?? ''),'photo_checksum_mismatch');
            $info=getimagesizefromstring($bytes);
            bj_operation_require($info && $info['mime']==='image/webp' && $info[0]>=400 && $info[1]>=250,'photo_format_rejected');
            $existing=get_posts(['post_type'=>'attachment','post_status'=>'inherit','numberposts'=>1,'meta_query'=>[['key'=>'_bj_photo_slug','value'=>$slug],['key'=>'_bj_photo_sha256','value'=>$item['sha256']]]]);
            if ($existing) {
                $attachment=$existing[0]->ID;
            } else {
                $filename=wp_unique_filename($upload['path'],$slug.'.webp');
                $path=$upload['path'].'/'.$filename;
                bj_operation_require(!file_exists($path) && !is_link($path),'photo_collision');
                bj_operation_write($path,$bytes,0644);
                $attachment=wp_insert_attachment(['post_mime_type'=>'image/webp','post_title'=>$item['title'],'post_status'=>'inherit'],$path,0,true);
                bj_operation_require(!is_wp_error($attachment),'media_import_failed');
                wp_update_attachment_metadata($attachment,wp_generate_attachment_metadata($attachment,$path));
                update_post_meta($attachment,'_bj_photo_slug',$slug);
                update_post_meta($attachment,'_bj_photo_sha256',$item['sha256']);
                update_post_meta($attachment,'_wp_attachment_image_alt',$item['alt']);
            }
            $meta=wp_get_attachment_metadata($attachment);
            bj_operation_require(!empty($meta['width']) && !empty($meta['height']),'media_metadata_missing');
            $manifest[$slug]=['id'=>(int)$attachment,'url'=>wp_get_attachment_url($attachment),'width'=>(int)$meta['width'],'height'=>(int)$meta['height']];
        }
        echo wp_json_encode(['ok'=>true,'operation'=>'import','backup_id'=>$release,'manifest'=>$manifest,'domain'=>'brincolinesjumping.com']);
        return;
    }

    $content=$payload['content'] ?? '';
    bj_operation_validate_blocks($content,$operation==='publish');
    if ($operation==='publish') {
        $manifest=$payload['manifest'] ?? [];
        bj_operation_require(isset($manifest['mickey-minnie']),'real_hero_manifest_missing');
        foreach($manifest as $slug=>$item) {
            $attachment=(int)$item['id'];
            bj_operation_require(get_post_type($attachment)==='attachment' && get_post_meta($attachment,'_bj_photo_slug',true)===$slug,'real_attachment_not_verified');
            bj_operation_require(wp_get_attachment_url($attachment)===$item['url'],'attachment_url_changed');
        }
    }
    $files=$payload['plugin_files'] ?? [];
    bj_operation_require(count($files)===2 && isset($files['brincolines-landing.php'],$files['landing.css']),'plugin_payload_incomplete');
    if (!is_dir($plugin_dir)) bj_operation_require(mkdir($plugin_dir,0755),'plugin_directory_failed');
    if (is_file($plugin_dir.'/brincolines-landing.php')) bj_operation_require(strpos(file_get_contents($plugin_dir.'/brincolines-landing.php'),'Brincolines Jumping · Landing')!==false,'existing_plugin_not_owned');
    // The Terminal uses umask 077 for private backups/staging. Public CSS
    // needs traversal permissions on this owned plugin directory.
    bj_operation_require(realpath($plugin_dir)===realpath(WP_PLUGIN_DIR).'/brincolines-landing','plugin_directory_scope');
    bj_operation_require(chmod($plugin_dir,0755),'plugin_directory_permissions_failed');
    foreach($files as $file=>$bytes) bj_operation_write($plugin_dir.'/'.$file,$bytes,0644);
    $activated=activate_plugin($plugin,'',false,true);
    bj_operation_require(!is_wp_error($activated),'plugin_activation_failed');
    $target=$front;
    if ($operation==='draft') {
        $target=$draft;
        if (!$target) {
            $target=wp_insert_post(['post_type'=>'page','post_title'=>'Brincolines Jumping · Portada en preparación','post_name'=>'brincolines-jumping-preview','post_status'=>'draft'],true);
            bj_operation_require(!is_wp_error($target),'draft_creation_failed');
            update_option('bj_landing_draft_id',$target,false);
            update_post_meta($target,'_bj_preview','1');
        }
    }
    wp_save_post_revision($target);
    // Replace the retired Elementor template in the same update. WordPress
    // otherwise writes the content before rejecting that invalid template.
    $result=wp_update_post(wp_slash(['ID'=>$target,'post_title'=>'Brincolines Jumping','post_content'=>$content,'post_status'=>$operation==='publish'?'publish':'draft','page_template'=>'default','comment_status'=>'closed','ping_status'=>'closed']),true);
    bj_operation_require(!is_wp_error($result),'page_update_failed');
    update_post_meta($target,'_bj_landing','1');
    update_post_meta($target,'_wp_page_template','default');
    foreach(['_elementor_data','_elementor_edit_mode','_elementor_template_type','_elementor_controls_usage'] as $key) delete_post_meta($target,$key);
    $changed=[$target];
    if ($operation==='publish') {
        set_post_thumbnail($target,(int)$payload['manifest']['mickey-minnie']['id']);
        update_option('blogname','Brincolines Jumping');
        update_option('blogdescription','Renta de brincolines en Aguascalientes');
        update_option('WPLANG','es_MX');
        if (get_post_type(13)==='page' && get_post_field('post_name',13)==='contact-us') {
            $contact_result=wp_update_post(['ID'=>13,'post_status'=>'draft','page_template'=>'default'],true);
            bj_operation_require(!is_wp_error($contact_result),'demo_contact_update_failed');
            $changed[]=13;
        }
    }
    $after=['posts'=>[],'options'=>[],'plugin_files'=>[]];
    foreach($changed as $id) {
        $managed=[];
        foreach(['_bj_landing','_wp_page_template','_elementor_data','_elementor_edit_mode','_elementor_template_type','_elementor_controls_usage','_thumbnail_id'] as $key) $managed[$key]=get_post_meta($id,$key);
        $after['posts'][$id]=['content_sha256'=>hash('sha256',get_post_field('post_content',$id)),'status'=>get_post_status($id),'title'=>get_post_field('post_title',$id),'managed_meta'=>$managed];
    }
    foreach(array_keys($before['options']) as $key) $after['options'][$key]=get_option($key,null);
    foreach(array_keys($files) as $file) $after['plugin_files'][$file]=hash_file('sha256',$plugin_dir.'/'.$file);
    bj_operation_write($backup_dir.'/after.json',wp_json_encode($after));
    wp_cache_flush();
    echo wp_json_encode(['ok'=>true,'operation'=>$operation,'backup_id'=>$release,'page_id'=>(int)$target,'post_status'=>get_post_status($target),'active_theme'=>get_option('stylesheet'),'native_blocks'=>true,'domain'=>'brincolinesjumping.com']);
} catch(Throwable $error) {
    // Fixed error labels only. Never disclose account paths, shell/session data or payloads.
    $reason=$error instanceof RuntimeException && preg_match('/^[a-z0-9_]+$/',$error->getMessage())?$error->getMessage():'operation_failed';
    echo wp_json_encode(['ok'=>false,'reason'=>$reason]);
}
