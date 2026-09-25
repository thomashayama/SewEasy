"""Local sign-in configuration without accessing real credentials or storage."""
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


CONFIG_SOURCE = Path(__file__).parent / 'webapp' / 'config.py'


class AuthConfigTest(unittest.TestCase):
    def load_config(self, dotenv=None, env=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'webapp' / 'config.py'
            config.parent.mkdir()
            config.write_text(CONFIG_SOURCE.read_text(encoding='utf-8'), encoding='utf-8')
            if dotenv is not None:
                (root / '.env').write_text(dotenv, encoding='utf-8')
            with patch.dict(os.environ, {'JWT_SECRET': 'test-session-key', **(env or {})}, clear=True):
                return runpy.run_path(str(config))

    def test_local_oauth_is_available_without_shell_exports(self):
        config = self.load_config(
            'GOOGLE_CLIENT_ID=local-client\nGOOGLE_CLIENT_SECRET="local-secret"\n'
            'GOOGLE_REDIRECT_URI=http://localhost:8080/auth/callback\n')
        self.assertTrue(config['google_configured']())
        self.assertEqual(config['GOOGLE_CLIENT_ID'], 'local-client')
        self.assertEqual(config['GOOGLE_CLIENT_SECRET'], 'local-secret')
        self.assertEqual(config['GOOGLE_REDIRECT_URI'], 'http://localhost:8080/auth/callback')

    def test_environment_overrides_local_values_and_can_disable_sign_in(self):
        dotenv = 'GOOGLE_CLIENT_ID=local-client\nGOOGLE_CLIENT_SECRET=local-secret\n'
        config = self.load_config(dotenv, {
            'GOOGLE_CLIENT_ID': 'deployment-client',
            'GOOGLE_CLIENT_SECRET': 'deployment-secret',
            'GOOGLE_REDIRECT_URI': 'https://example.test/auth/callback',
        })
        self.assertEqual(config['GOOGLE_CLIENT_ID'], 'deployment-client')
        self.assertEqual(config['GOOGLE_CLIENT_SECRET'], 'deployment-secret')
        self.assertEqual(config['GOOGLE_REDIRECT_URI'], 'https://example.test/auth/callback')
        disabled = self.load_config(dotenv, {'GOOGLE_CLIENT_SECRET': ''})
        self.assertFalse(disabled['google_configured']())

    def test_missing_or_incomplete_credentials_keep_sign_in_disabled(self):
        for dotenv in (None, '', 'GOOGLE_CLIENT_ID=client\n',
                       'GOOGLE_CLIENT_ID=client\nGOOGLE_CLIENT_SECRET=\n'):
            with self.subTest(dotenv=dotenv):
                self.assertFalse(self.load_config(dotenv)['google_configured']())

    def test_local_oauth_does_not_change_database_or_session_configuration(self):
        config = self.load_config(
            'GOOGLE_CLIENT_ID=local-client\nGOOGLE_CLIENT_SECRET=local-secret\n'
            'DATABASE_URL=postgresql://unused.example/test\nJWT_SECRET=another-key\n',
            {'DATABASE_URL': 'sqlite:///data/current.db'})
        self.assertEqual(config['DATABASE_URL'], 'sqlite:///data/current.db')
        self.assertEqual(config['JWT_SECRET'], 'test-session-key')

    def test_postgres_urls_name_the_installed_driver(self):
        # SQLAlchemy 2.1 made psycopg 3 the default for postgresql://; the image installs psycopg2.
        for url in ('postgres://user:pw@db.example:5432/app', 'postgresql://user:pw@db.example:5432/app'):
            with self.subTest(url=url):
                self.assertEqual(self.load_config(env={'DATABASE_URL': url})['DATABASE_URL'],
                                 'postgresql+psycopg2://user:pw@db.example:5432/app')
        explicit = 'postgresql+psycopg2://user@db.example/app'
        self.assertEqual(self.load_config(env={'DATABASE_URL': explicit})['DATABASE_URL'], explicit)
        self.assertEqual(self.load_config()['DATABASE_URL'], 'sqlite:///data/seweasy.db')


if __name__ == '__main__':
    unittest.main()
