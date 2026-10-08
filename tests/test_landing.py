import importlib.util
import json
from pathlib import Path
import unittest
import urllib.parse
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build-landing.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
CONFIG=json.loads((ROOT/'content/catalog.json').read_text())


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.h1=0
        self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a':self.links.append(attrs.get('href',''))
        if tag=='h1':self.h1+=1
        if 'id' in attrs:self.ids.append(attrs['id'])


def photos():
    return {m['slug']:{'id':100+i,'url':'https://brincolinesjumping.com/wp-content/uploads/2026/10/'+m['slug']+'.webp','width':900,'height':600} for i,m in enumerate(CONFIG['models'])}


class LandingTests(unittest.TestCase):
    def test_missing_secondary_photo_does_not_block_real_hero(self):
        manifest=photos()
        del manifest['barco-escalador']
        content,missing=builder.build(CONFIG,manifest)
        self.assertIn('barco-escalador',missing)
        self.assertNotIn('bj-pending-photo',content)

    def test_production_refuses_missing_hero(self):
        with self.assertRaisesRegex(ValueError,'Original hero photo file required'):
            builder.build(CONFIG,{})

    def test_external_and_insecure_photo_urls_rejected(self):
        for bad in ['https://otro-dominio.com/wp-content/uploads/p.webp','http://brincolinesjumping.com/wp-content/uploads/p.webp','https://brincolinesjumping.com.evil.test/wp-content/uploads/p.webp','https://user:secret@brincolinesjumping.com/wp-content/uploads/p.webp','https://brincolinesjumping.com/wp-content/uploads/../other/p.webp']:
            manifest=photos()
            manifest['frozen']['url']=bad
            with self.subTest(url=bad),self.assertRaises(ValueError):builder.build(CONFIG,manifest)

    def test_all_ctas_target_confirmed_number_and_model_context(self):
        content,missing=builder.build(CONFIG,photos())
        parser=Links();parser.feed(content)
        links=[link for link in parser.links if link.startswith('https://wa.me/')]
        self.assertGreaterEqual(len(links),14)
        messages=[]
        for link in links:
            parsed=urllib.parse.urlsplit(link)
            self.assertEqual(parsed.path,'/524491911663')
            messages.append(urllib.parse.parse_qs(parsed.query)['text'][0])
        for model in CONFIG['models']:self.assertTrue(any(model['name'] in message for message in messages))
        self.assertFalse(missing)

    def test_single_h1_and_internal_navigation_resolve(self):
        content,_=builder.build(CONFIG,photos())
        parser=Links();parser.feed(content)
        self.assertEqual(parser.h1,1)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for link in parser.links:
            if link.startswith('#'):self.assertIn(link[1:],parser.ids)

    def test_private_draft_is_explicitly_incomplete(self):
        content,missing=builder.build(CONFIG,{},True)
        self.assertEqual(len(missing),len(CONFIG['models']))
        self.assertIn('Foto original pendiente',content)
        self.assertNotIn('<!-- wp:image',content)

    def test_no_mockup_prices_old_numbers_or_fabricated_reviews(self):
        content,_=builder.build(CONFIG,photos())
        for obsolete in ['$900','$1,500','$2,200','$3,000','4491129572','4492777314','CDMX','123-456','Service 1','Client Testimonials','★★★★★','Acuáticos']:
            self.assertNotIn(obsolete,content)
        self.assertNotIn('wp:html',content)
        self.assertNotIn('wp:shortcode',content)


if __name__=='__main__':unittest.main()
