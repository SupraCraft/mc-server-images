"""The H97 acoustic fixtures are synthetic, deterministic and mutually distinct."""
import hashlib
import importlib.util
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"interview_clap_audio_h97.py"
spec=importlib.util.spec_from_file_location("h97_clap",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FrozenAudioTests(unittest.TestCase):
    def test_model_revision_weights_and_prompt_are_fixed(self):
        self.assertEqual(m.MODEL_REVISION,"8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a")
        self.assertEqual(m.WEIGHTS_SHA256,"1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb")
        self.assertEqual(len(m.CAPTIONS),4)
        self.assertEqual(m.SR,48000)
    @unittest.skipUnless(importlib.util.find_spec('numpy') is not None, 'optional NumPy: dedicated audio-fixture-contract job pins and runs this test')
    def test_audio_generation_reproducible_and_distinguishable(self):
        import numpy as np
        one=m.produce_frozen_fixtures()
        two=m.produce_frozen_fixtures()
        self.assertEqual([label for label,_ in one],m.LABELS)
        hashes=[]
        for (a,xa),(b,xb) in zip(one,two):
            self.assertEqual(a,b)
            self.assertEqual(xa.shape,(m.SR*m.DURATION_SECONDS,))
            self.assertEqual(xa.dtype,np.float32)
            self.assertTrue(np.array_equal(xa,xb))
            self.assertLessEqual(np.max(np.abs(xa)),1.0)
            hashes.append(hashlib.sha256(xa.tobytes()).hexdigest())
        self.assertEqual(len(set(hashes)),4)
        self.assertTrue(np.all(one[-1][1]==0))
        self.assertGreater(np.mean(one[0][1]**2),np.mean(one[1][1]**2))
        self.assertGreater(np.mean(one[1][1]**2),0)


if __name__=="__main__":
    unittest.main()
