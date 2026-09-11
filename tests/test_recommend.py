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
    def test_release_window_and_future_rollout(self):
        def html(day):
            return '<h1>Release</h1><span>Rollout start on '+day+'</span><h2>Updates</h2><h3 id="a">Java</h3><p>Update</p>'
        index=' '.join('/whats-new/oneagent/sprint-'+str(i) for i in [5,4,3])
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'get_page',side_effect=[index,html('Sep 20, 2026'),html('Sep 01, 2026'),html('Jul 01, 2026')]):
            pages=r.fetch_releases({'channels':['oneagent'],'release_days':30},Path(tmp),r.date(2026,9,10))
            self.assertEqual(len(pages),1)
            self.assertTrue(pages[0]['url'].endswith('sprint-4'))
    def test_host_os_alias_and_postgres(self):
        data=r.rank([{'id':'H1','os_type':'OS_TYPE_LINUX','technologies':[{'type':'LINUX_SYSTEM'},{'type':'POSTGRE_SQL'}]}])
        self.assertEqual([x['technology'] for x in data['ranked']],['LINUX','POSTGRES'])

if __name__=='__main__': unittest.main()
