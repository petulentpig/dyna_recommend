import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import recommend as r

class PipelineTests(unittest.TestCase):
    def inventory(self):
        return r.rank([{'id':'P1','technologies':[{'type':'JAVA','version':'17'},{'type':'JAVA','version':'21'}]},
                       {'id':'P2','technologies':[{'type':'NODE_JS'}]}, {'id':'P3','technologies':None}])
    def test_duplicate_entity_and_null_inventory(self):
        data=self.inventory()
        self.assertEqual(data['ranked'][0]['entity_count'],1)
        self.assertEqual(data['ranked'][0]['prevalence_pct'],33.33)
        self.assertEqual(data['ranked'][0]['versions'],['17','21'])
        self.assertEqual(data['without_technologies'],1)
    def test_java_not_javascript_and_go_not_verb(self):
        self.assertNotIn('JAVA',r.mentioned('JavaScript change'))
        self.assertNotIn('GO',r.mentioned('Go to Settings'))
        self.assertIn('NODE_JS',r.mentioned('Node.js code module'))
    def test_unused_and_cross_technology_notes_are_held(self):
        notes=[{'id':'1','title':'Java fix','body':'Fixed tracing','date':'2026-09-01'},
               {'id':'2','title':'.NET fix','body':'Fixed tracing','date':'2026-09-01'},
               {'id':'3','title':'Java AWS Lambda fix','body':'Fixed tracing','date':'2026-09-01'},
               {'id':'4','title':'Java and Node.js integration','body':'Fixed tracing','date':'2026-09-01'}]
        selected=r.select(self.inventory(),[{'items':notes+notes}])
        self.assertEqual([n['id'] for n in selected['included']],['1'])
        self.assertEqual([n['id'] for n in selected['excluded']],['2'])
        self.assertEqual([n['id'] for n in selected['held']],['3','4'])
    def test_partial_and_spilled_results_rejected(self):
        for obj in [{'ok':False}, {'ok':True,'result':{'kind':'result-file'}},
                    {'ok':True,'context':{'has_more':True}},
                    {'ok':True,'result':{'kind':'records','records':[]}}]:
            with self.assertRaises(ValueError): r.records_from(obj,100)
        with self.assertRaises(ValueError):
            r.records_from({'ok':True,'result':{'kind':'records','records':[{}]}},1)
    def test_parser_separates_individual_fixes(self):
        html='''<h1>Release 1.2</h1><span>Rollout start on Sep 01, 2026</span>
        <h2>Features</h2><h3 id="java">Java feature</h3><p>New tracing.</p>
        <h2>Fixes and maintenance</h2><h3 id="fixes">GA</h3><ul>
        <li>Fixed .NET tracing.</li><li>Fixed Java tracing.</li></ul>'''
        page=r.parse_release(html,r.DOCS+'/whats-new/oneagent/sprint-2')
        self.assertEqual(len(page['items']),3)
        self.assertEqual(page['date'],'2026-09-01')
        selected=r.select(self.inventory(),[page])
        self.assertEqual(len(selected['included']),2)
        self.assertEqual(len(selected['excluded']),1)
    def test_parser_fails_when_source_layout_changes(self):
        with self.assertRaises(ValueError): r.parse_release('<h1>Oops</h1>','test')
    def test_approval_exports_reviewed_text_and_records_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            r.write_json(p/'review.json',{'customer':'Example'})
            (p/'email.txt').write_text('Human edited draft\n')
            r.approve(p,'Reviewer','review@example.com')
            self.assertIn(b'Human edited draft',(p/'approved.eml').read_bytes())
            self.assertEqual(r.load(p/'approval.json')['eml_sha256'],r.digest((p/'approved.eml').read_bytes()))
    def test_latest_release_skips_future_and_does_not_fetch_older(self):
        def html(version, day, content=True):
            return f'<h1>Release {version}</h1><span>Rollout start on {day}</span>'+('<h2>Updates</h2><h3 id="a">Java</h3><p>Update</p>' if content else '')
        index=' '.join('/whats-new/oneagent/sprint-'+str(i) for i in [5,4,3])
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'get_page',side_effect=[index,html('1.5','Sep 20, 2026',False),html('1.4','Sep 01, 2026')]) as get:
            pages=r.fetch_releases({'channels':['oneagent']},Path(tmp),r.date(2026,9,10))
            self.assertEqual(len(pages),1)
            self.assertEqual(pages[0]['version'],'1.4')
            self.assertEqual(get.call_count,3)

    def test_latest_release_is_used_even_if_old_window_would_exclude_it(self):
        html='<h1>Release 1.4</h1><span>Rollout start on Jan 01, 2026</span><h3 id="a">Java</h3><p>Update</p>'
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'get_page',side_effect=['/whats-new/oneagent/sprint-4',html]):
            pages=r.fetch_releases({'channels':['oneagent'],'release_days':1},Path(tmp),r.date(2026,9,10))
            self.assertEqual(pages[0]['version'],'1.4')

    def test_invalid_latest_release_does_not_fall_back(self):
        html='<h1>Release 1.4</h1><span>Rollout start on Sep 01, 2026</span>'
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'get_page',side_effect=['/whats-new/oneagent/sprint-4 /whats-new/oneagent/sprint-3',html]) as get:
            with self.assertRaisesRegex(ValueError,'no changes'):
                r.fetch_releases({'channels':['oneagent']},Path(tmp),r.date(2026,9,10))
            self.assertEqual(get.call_count,2)

    def test_each_channel_gets_its_own_latest_release(self):
        html='<h1>Release 1.4</h1><span>Rollout start on Sep 01, 2026</span><h3 id="a">Java</h3><p>Update</p>'
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'get_page',side_effect=['/whats-new/oneagent/sprint-4',html,'/whats-new/saas/sprint-5',html.replace('1.4','1.5')]):
            pages=r.fetch_releases({'channels':['oneagent','saas']},Path(tmp),r.date(2026,9,10))
            self.assertEqual([(p['channel'],p['version']) for p in pages],[('oneagent','1.4'),('saas','1.5')])

    def test_email_has_releases_and_ranking_even_without_matches(self):
        report={'included':[], 'customer':'Example', 'source_pages':[{'channel':'oneagent','version':'1.4','date':'2026-09-01','url':'https://example.com/release'}]}
        text=r.draft_text({'customer':'Example'},self.inventory(),report,r.date(2026,9,10))
        self.assertIn('OneAgent 1.4',text)
        self.assertIn('1 | Java | 1 | 33.33% | 0',text)
        self.assertIn('2 | Node.js | 1 | 33.33% | 0',text)
        self.assertIn('No confirmed technology matches',text)
        self.assertIn('OneAgent 1.4',r.email_subject(report))

    def test_host_os_alias_and_postgres(self):
        data=r.rank([{'id':'H1','os_type':'OS_TYPE_LINUX','technologies':[{'type':'LINUX_SYSTEM'},{'type':'POSTGRE_SQL'}]}])
        self.assertEqual([x['technology'] for x in data['ranked']],['LINUX','POSTGRES'])

class InstanceSelectionTests(unittest.TestCase):
    def test_interactive_run_asks_for_instance(self):
        with patch.object(r.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='https://Example.apps.dynatrace.com/') as ask:
            self.assertEqual(r.choose_environment(), 'https://example.apps.dynatrace.com')
            self.assertIn('Dynatrace instance', ask.call_args[0][0])

    def test_noninteractive_run_requires_user_answer(self):
        with patch.object(r.sys.stdin, 'isatty', return_value=False), patch('builtins.input') as ask:
            with self.assertRaisesRegex(ValueError, 'Ask the user'):
                r.choose_environment()
            ask.assert_not_called()

    def test_supplied_instance_is_not_asked_again(self):
        with patch('builtins.input') as ask:
            self.assertEqual(r.choose_environment('https://example.apps.dynatrace.com:443/'), 'https://example.apps.dynatrace.com')
            ask.assert_not_called()

    def test_bad_or_empty_urls_rejected(self):
        for url in ['', 'example.apps.dynatrace.com', 'http://example.com',
                    'https://user:secret@example.com', 'https://example.com?token=secret',
                    'https://example.com/#dashboard', 'https://bad host.com']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                r.normalize_environment(url)

    def contexts(self, safety='readonly'):
        return [{'Name':'customer', 'Environment':'https://example.apps.dynatrace.com/', 'SafetyLevel':safety}]

    def test_matching_readonly_context_is_accepted(self):
        with patch.object(r, 'dtctl', return_value=self.contexts()) as call:
            self.assertEqual(r.verify_environment({'context':'customer'}, 'https://example.apps.dynatrace.com'), 'https://example.apps.dynatrace.com')
            self.assertEqual(call.call_args[0][1:3], ('config','get-contexts'))

    def test_wrong_instance_stops_before_discovery_and_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'dtctl', return_value=self.contexts()) as call:
            out=Path(tmp)/'run'
            with self.assertRaisesRegex(ValueError, 'does not match'):
                r.run({'context':'customer'},out,'https://other.apps.dynatrace.com')
            self.assertFalse(out.exists())
            self.assertEqual(call.call_count,1)
            self.assertEqual(call.call_args[0][1:3], ('config','get-contexts'))

    def test_missing_or_writable_context_rejected(self):
        for contexts in [[], self.contexts('readwrite-all')]:
            with patch.object(r, 'dtctl', return_value=contexts), self.assertRaises(ValueError):
                r.verify_environment({'context':'customer'}, 'https://example.apps.dynatrace.com')

if __name__=='__main__': unittest.main()
