import tempfile
from pathlib import Path
import unittest
import legal_build as law
class LegalTests(unittest.TestCase):
    def test_citations(self):
        text='W.S. § 16-4-404; 42 U.S.C. 12132; 28 C.F.R. 35.130; 2015 WY 148; 590 U.S. 255; Cheyenne Municipal Code 2.04.010'
        refs=list(law.references(text));self.assertEqual(len(refs),6)
        for r in refs:self.assertEqual(text[r['start']:r['end']],r['literal'])
    def test_host_boundary(self):
        for u in ['http://wyoleg.gov/file.pdf','https://wyoleg.gov.evil.example/x','https://127.0.0.1/x','https://wyoleg.gov:444/x']:
            with self.assertRaises(ValueError):law.check_url(u)
        self.assertEqual(law.check_url('https://wyoleg.gov/statutes/compress/title16.pdf'),'https://wyoleg.gov/statutes/compress/title16.pdf')
    def test_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'blobs').mkdir();item=law.payload(p,b'primary text');law.verify_payload(p,item);(p/item['parts'][0]['path']).write_bytes(b'bad')
            with self.assertRaises(ValueError):law.verify_payload(p,item)
if __name__=='__main__':unittest.main()
