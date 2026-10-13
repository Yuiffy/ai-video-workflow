import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('voice_dataset', Path(__file__).parents[1]/'tools/build_voice_dataset.py')
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)


class VoiceDatasetTest(unittest.TestCase):
    def test_identity_and_boundaries(self):
        content = '''1
00:05:00,000 --> 00:05:04,000
[岁己SUI 0.85] 第一句

2
00:05:04,200 --> 00:05:08,000
[岁己SUI 0.78] 第二句

3
00:05:08,100 --> 00:05:11,000
[UNKNOWN] 其他人

4
00:05:11,200 --> 00:05:15,000
[岁己SUI 0.89] 第三句

5
00:05:20,000 --> 00:05:25,000
[岁己SUI 0.60] 低置信度
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.srt'
            path.write_text(content, encoding='utf-8')
            rows = dataset.parse_candidates(dict(srt=str(path),date='2026_09_24',media='test.flv'),.76)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['start'],300)
        self.assertEqual(rows[0]['end'],308)
        self.assertEqual(rows[0]['score'],.78)
        self.assertEqual(rows[1]['start'],311.2)
        self.assertNotIn('其他人',' '.join(r['text'] for r in rows))

    def test_timestamp(self):
        self.assertAlmostEqual(dataset.seconds('02:13:04,123'),7984.123)


if __name__=='__main__':
    unittest.main()
