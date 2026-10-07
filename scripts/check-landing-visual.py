#!/usr/bin/env python3
"""Browser checks and screenshots; does not claim field Core Web Vitals."""
import argparse
import json
from pathlib import Path
import shutil
import ssl
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ALLOWED={'brincolinesjumping.com','www.brincolinesjumping.com'}


def tls_bridge(route):
    # Browser-specific proxy CA incompatibility: urllib still validates TLS.
    # This is for visual checks only, not performance measurements.
    parsed=urllib.parse.urlsplit(route.request.url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED or parsed.username or parsed.password:
        route.abort();return
    try:
        request=urllib.request.Request(route.request.url,headers={'Accept-Encoding':'identity','User-Agent':'Mozilla/5.0 BrincolinesVisualCheck'})
        with urllib.request.urlopen(request,context=ssl.create_default_context(),timeout=20) as response:
            final=urllib.parse.urlsplit(response.url)
            if final.hostname not in ALLOWED or final.scheme!='https':
                route.abort();return
            headers={key:value for key,value in response.headers.items() if key.lower() not in {'content-length','content-encoding','transfer-encoding','connection'}}
            route.fulfill(status=response.status,headers=headers,body=response.read(6_000_000))
    except Exception:
        route.abort()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft-file',type=Path)
    parser.add_argument('--tls-bridge',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('.local/landing/visual'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    executable=shutil.which('chromium') or shutil.which('google-chrome')
    if not executable:raise SystemExit('Chrome/Chromium is required for visual checks')
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        for width in [375,390,430,768,1440]:
            page=browser.new_page(viewport={'width':width,'height':844},is_mobile=width<600,has_touch=width<600)
            errors=[]
            page.on('pageerror',lambda error:errors.append(type(error).__name__))
            if not args.draft_file and not args.tls_bridge:
                page.add_init_script('''window.bjPerformance={lcp_ms:null,cls:0};
                new PerformanceObserver(list=>{for(const entry of list.getEntries())window.bjPerformance.lcp_ms=entry.startTime}).observe({type:'largest-contentful-paint',buffered:true});
                new PerformanceObserver(list=>{for(const entry of list.getEntries())if(!entry.hadRecentInput)window.bjPerformance.cls+=entry.value}).observe({type:'layout-shift',buffered:true});''')
            if args.tls_bridge:page.route('**/*',tls_bridge)
            if args.draft_file:
                page.set_content(args.draft_file.read_text(),wait_until='networkidle')
            else:
                response=page.goto('https://brincolinesjumping.com/',wait_until='networkidle',timeout=60000)
                if response.status!=200:raise RuntimeError('Public homepage did not return HTTP200')
            lab_performance=None
            if not args.draft_file and not args.tls_bridge:
                page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                lab_performance=page.evaluate('()=>({...window.bjPerformance,scope:"Chrome lab, unthrottled, initial viewport"})')
            # Trigger below-fold lazy images while preserving final screenshot position.
            if not args.draft_file:
                # Visit each real image: fast page jumps can skip lazy-load
                # intersections on an unthrottled hosted runner.
                for photo in page.locator('.bj-landing img').all():
                    photo.scroll_into_view_if_needed()
                    try:
                        page.wait_for_function('(x)=>x.complete && x.naturalWidth>0',arg=photo.element_handle(),timeout=30000)
                    except Exception:
                        missing=page.evaluate("()=>[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>({src:x.currentSrc||x.src,alt:x.alt,loading:x.loading}))")
                        (args.output/'image-load-failure.json').write_text(json.dumps({'width':width,'missing':missing},ensure_ascii=False,indent=2))
                        print(json.dumps({'scope':'public homepage','width':width,'failure':'real_image_loading','missing':missing},ensure_ascii=False))
                        raise
                page.evaluate('()=>Promise.all([...document.images].map(x=>x.decode()))')
                page.evaluate('scrollTo(0,0)')
            data=page.evaluate('''() => ({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,h1:document.querySelectorAll('h1').length,ctas:[...document.querySelectorAll('.wp-block-button__link')].map(a=>({width:a.getBoundingClientRect().width,height:a.getBoundingClientRect().height,href:a.href})),heroCtaBottom:document.querySelector('.bj-hero .wp-block-button__link').getBoundingClientRect().bottom,hero:document.querySelector('.bj-hero-photo img')?{loading:document.querySelector('.bj-hero-photo img').loading,priority:document.querySelector('.bj-hero-photo img').fetchPriority}:null,photoCount:document.querySelectorAll('.bj-landing img').length,pendingPlaceholders:document.querySelectorAll('.bj-pending-photo').length})''')
            data['floating']=page.locator('.bj-floating').evaluate('''x=>({text:x.textContent.trim(),position:getComputedStyle(x).position,left:x.getBoundingClientRect().left,right:x.getBoundingClientRect().right,top:x.getBoundingClientRect().top,bottom:x.getBoundingClientRect().bottom})''')
            data['layout']=page.evaluate('''()=>({headerHeight:document.querySelector('.bj-header').getBoundingClientRect().height,catalogColumns:getComputedStyle(document.querySelector('.bj-catalog')).gridTemplateColumns.split(' ').length,galleryColumns:getComputedStyle(document.querySelector('.bj-gallery')).gridTemplateColumns.split(' ').length,heroPhotoBottom:document.querySelector('.bj-hero-photo').getBoundingClientRect().bottom})''')
            data['lab_performance']=lab_performance
            faq=page.locator('.bj-faq details').first
            faq.locator('summary').focus();page.keyboard.press('Enter')
            data['faq_keyboard_opens']=faq.evaluate('x=>x.open')
            data['script_errors']=errors
            if width==390:
                page.evaluate('scrollTo(0,0)')
                page.screenshot(path=str(args.output/'iphone.png'),full_page=True)
                page.screenshot(path=str(args.output/'iphone-first-screen.png'))
            results.append(data);page.close()
        browser.close()
    report={'scope':'private draft' if args.draft_file else 'public homepage','tls_bridge':args.tls_bridge,'checks':results,'field_performance_measured':False}
    (args.output/'visual.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    failures=[]
    for result in results:
        if result['overflow'] or result['h1']!=1 or not result['faq_keyboard_opens'] or result['script_errors']:failures.append('layout_or_accessibility')
        for cta in result['ctas']:
            if cta['width']<44 or cta['height']<44 or not cta['href'].startswith('https://wa.me/524491911663?text='):failures.append('cta')
        if result['width']<600 and result['heroCtaBottom']>844:failures.append('hero_cta_below_first_screen')
        floating=result['floating']
        if floating['text']!='Contratar ahora' or floating['position']!='fixed' or floating['left']<0 or floating['right']>result['width'] or floating['bottom']>844:failures.append('floating_cta')
        layout=result['layout']
        expected_catalog=1 if result['width']<600 else (2 if result['width']<900 else 3)
        expected_gallery=2 if result['width']<600 else 4
        if layout['catalogColumns']!=expected_catalog or layout['galleryColumns']!=expected_gallery:failures.append('responsive_grid')
        if result['width']<600 and (layout['headerHeight']>100 or layout['heroPhotoBottom']>result['heroCtaBottom'] or result['heroCtaBottom']>floating['top']):failures.append('mobile_first_screen')
        if not args.draft_file:
            if result['pendingPlaceholders'] or not result['hero'] or result['hero']['loading']!='eager' or result['hero']['priority']!='high':failures.append('real_hero')
    print(json.dumps({'scope':report['scope'],'widths_tested':[r['width'] for r in results],'passed':not failures,'failure_categories':sorted(set(failures)),'lab_performance':[r['lab_performance'] for r in results] if not args.tls_bridge and not args.draft_file else None}))
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
