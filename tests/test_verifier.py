"""Check real captured values and reject misleading or incomplete evidence."""
import gzip
from pathlib import Path
import tempfile
import unittest

from tools.verify_results import verify

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / 'docs/evidence/gpu-readback-20-suites.txt.gz'


class VerifierTests(unittest.TestCase):
    def setUp(self):
        lines = gzip.decompress(TRACE.read_bytes()).decode().splitlines()
        end = next(i for i, line in enumerate(lines) if line.startswith('ML_PASS '))
        self.suite = lines[:end + 1]

    def check_lines(self, lines):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'capture.txt'
            path.write_text('\n'.join(lines) + '\n')
            return verify(path)

    def test_hardware_capture(self):
        self.assertEqual(verify(TRACE), dict(verified=True, suites=20,
                         gpu_dispatches=120, values=10920, exact_rational_match=True))

    def test_reject_missing_value(self):
        i = next(i for i, line in enumerate(self.suite) if line.startswith('ML_VALUE '))
        with self.assertRaises(ValueError):
            self.check_lines(self.suite[:i] + self.suite[i + 1:])

    def test_reject_duplicate_value(self):
        value = next(line for line in self.suite if line.startswith('ML_VALUE '))
        with self.assertRaises(ValueError):
            self.check_lines(self.suite[:-1] + [value, self.suite[-1]])

    def test_reject_wrong_value(self):
        with self.assertRaises(ValueError):
            self.check_lines([line.replace('actual=', 'actual=999') if line.startswith('ML_VALUE ') else line
                              for line in self.suite])

    def test_reject_unknown_case(self):
        with self.assertRaises(ValueError):
            self.check_lines([line.replace('round=0', 'round=3') for line in self.suite])

    def test_reject_guard_error(self):
        with self.assertRaises(ValueError):
            self.check_lines([line.replace('guard_errors=0', 'guard_errors=1') for line in self.suite])

    def test_reject_missing_pass(self):
        with self.assertRaises(ValueError):
            self.check_lines(self.suite[:-1])

    def test_reject_duplicate_completion(self):
        with self.assertRaises(ValueError):
            self.check_lines([line.replace('token=200000001', 'token=100000001') for line in self.suite])

    def test_reject_duplicate_result(self):
        result = next(line for line in self.suite if line.startswith('ML_RESULT '))
        with self.assertRaises(ValueError):
            self.check_lines(self.suite[:-1] + [result, self.suite[-1]])

    def test_reject_failure_after_pass(self):
        with self.assertRaises(ValueError):
            self.check_lines(self.suite + ['ML_FAIL cleanup'])


if __name__ == '__main__':
    unittest.main()
