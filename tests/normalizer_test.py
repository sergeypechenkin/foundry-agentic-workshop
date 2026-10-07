import contextlib
import io
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'form-extraction'))

from utils.normalizer import _normalize_email, _valid_email, normalize_fields


class EmailValidationTest(unittest.TestCase):
    def test_valid_addresses(self):
        for value in (
            'user@example.com',
            'User.Name+tag@Sub.Example.co.uk',
            "o'connor@example.com",
            'user@my-domain.com',
            'x@y.co',
            'user@xn--bcher-kva.example',
            'a' * 64 + '@example.com',
            'user@' + 'a' * 63 + '.com',
            'a' * 64 + '@' + '.'.join(('b' * 63, 'c' * 63, 'd' * 61)),
        ):
            with self.subTest(value=value):
                self.assertTrue(_valid_email(value))

    def test_invalid_addresses(self):
        for value in (
            '', ' ', '\t\r\n', None, 123,
            'user', 'user@example', '@example.com', 'user@',
            'user@@example.com', 'user@example.com@other.com',
            '.user@example.com', 'user.@example.com', 'user..name@example.com',
            'user@.example.com', 'user@example..com', 'user@example.com.',
            'user@-example.com', 'user@example-.com', 'user@exam_ple.com',
            'user name@example.com', 'user@exam ple.com',
            'user\t@example.com', 'user@exam\nple.com',
            'user<name@example.com', 'user,name@example.com',
            'user@example.com/path', 'user@example.com:25',
            'a' * 65 + '@example.com',
            'user@' + 'a' * 64 + '.com',
            'a' * 64 + '@' + '.'.join(('b' * 63, 'c' * 63, 'd' * 62)),
        ):
            with self.subTest(value=value):
                self.assertFalse(_valid_email(value))

    def test_surrounding_whitespace(self):
        for value in (
            ' User.Name+tag@Example.COM ',
            '\tUser.Name+tag@Example.COM\r\n',
            '\u00a0User.Name+tag@Example.COM\u00a0',
        ):
            with self.subTest(value=value):
                self.assertEqual(_normalize_email(value), 'user.name+tag@example.com')
                self.assertTrue(_valid_email(value))
                self.assertTrue(_valid_email(_normalize_email(value)))

    def test_normalization_does_not_hide_invalid_input(self):
        for value in ('user name@example.com', 'user@exam\tple.com', 'user@exam\nple.com'):
            with self.subTest(value=value):
                self.assertEqual(_normalize_email(value), value)
                self.assertFalse(_valid_email(_normalize_email(value)))
        self.assertEqual(_normalize_email(' \t\n'), '')

    def test_registered_rule_and_confidence(self):
        doc_intelligence = ModuleType('utils.doc_intelligence')
        doc_intelligence.get_value_confidence = Mock(return_value=0.8)
        fields = {
            'Email': ' User@Example.COM ',
            'Email address': 'user name@example.com',
            'E-mail': '',
            'Phone': '01234 567890',
            'Other': ' unchanged ',
            'Nested': {'Email': 'user@example.org'},
            'Rows': [{'Email': 'user@example.net'}],
            'Email count': 2,
        }
        with patch.dict(sys.modules, {'utils.doc_intelligence': doc_intelligence}):
            with contextlib.redirect_stdout(io.StringIO()):
                result = normalize_fields(fields, {'word': 0.8})
                without_confidence = normalize_fields(fields)
        self.assertEqual(result['Email'], {'value': 'user@example.com', 'confidence': 0.95})
        self.assertEqual(result['Email address'], {'value': 'user name@example.com', 'confidence': 0.5})
        self.assertEqual(result['E-mail'], {'value': '', 'confidence': 0.5})
        self.assertEqual(result['Phone'], {'value': '01234567890', 'confidence': 0.95})
        self.assertEqual(result['Other'], {'value': ' unchanged ', 'confidence': 0.8})
        self.assertEqual(result['Nested']['Email']['confidence'], 0.95)
        self.assertEqual(result['Rows'][0]['Email']['confidence'], 0.95)
        self.assertEqual(result['Email count'], 2)
        self.assertEqual(without_confidence['Email'], 'user@example.com')
        self.assertEqual(without_confidence['Email address'], 'user name@example.com')
        self.assertEqual(without_confidence['E-mail'], '')


if __name__ == '__main__':
    unittest.main()
