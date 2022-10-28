from unittest import mock
from kill_hogs import kill_hogs
import mailtest
import random
import time
import unittest
import yaml


class PostToSlackTestcase(unittest.TestCase):
    def mocked_requests_post(*args, **kwargs):
        """
        Adapted from an answer here:
        https://stackoverflow.com/questions/15753390/how-can-i-mock-requests-and-the-response
        """

        class MockResponse:
            def __init__(self, json_data, status_code):
                self.json_data = json_data
                self.status_code = status_code
                self.text = "MOcked successfully."

            def json(self):
                return self.json_data

        if args[0] == 'https://hooks.slack.com/services/some/random/string':
            return MockResponse({"key1": "value1"}, 200)

        return MockResponse(None, 404)

    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_post_to_slack(self, mock_get):
        """
        Call post_to_slack and make sure requests.post was called with the
        right parameters.
        """
        kill_hogs.post_to_slack(
            'Hello world',
            slack_url='https://hooks.slack.com/services/some/random/string')

        # assert that our mocked function was called with the right parameters
        self.assertIn(
            mock.call(
                'https://hooks.slack.com/services/some/random/string',
                data=b'{"channel": "#kill-hogs", '
                b'"username": "kill-hogs", "text": "Hello world", '
                b'"icon_emoji": ":scales:"}',
                headers={'Content-Type': 'application/json'}),
            mock_get.call_args_list)


class KillhogsTestCase(unittest.TestCase):

    dummy_config = '''
---
slack_url: 'https://hooks.slack.com/services/some/random/string'
user_pattern: '^((s|p|f)[0-9]{5,7}|umcg-[a-z]{3,10})'
software_whitelist: ['git']
from_address: 'root@some-cluster.org'
#Port at which local mailserver is running.
mail_server_port: 1025
terminal_warning: |
    Please submit your processes as a job.
    Your processes have been killed and this incident has been reported.
    For more information, see https://redmine.hpc.rug.nl/redmine/projects/peregrine/wiki/FAQ
mail_body: |
    Dear Cluster user,

    We detected resource intensive processes on the login node running from your account.
    The login node of the cluster is used by all users of the cluster to login and submit jobs. A high load on the login node will impair the usability of the cluster for other users.
    It is therefore not allowed to run processes that take a significant amount of memory or cpu power. We have a short queue available if you quickly want to test something. Alternatively you could use the inter>

    for more information see the cluster wiki:
    https://wiki.example.org

    The HPC team.

    The output of our check follows below:
mail_body_request_only: |
      Dear cluster user,

      We detected resource intensive processes on the interactive node running from your account.
      Your processes were killed upon a request by another user.
      The interactive node is meant for more heavy processes but it should still be available to other users.

      for more information see the cluster wiki:
      https://wiki.example.org

      The HPC team.

      The output of our check follows below:
'''
    config_dict = yaml.load(dummy_config, Loader=yaml.Loader)

    def mocked_subprocess_run(*args, **kwargs):
        """
        """

        class MockedCompletedProcess:
            def __init__(self, stdout, stderr=None):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = 0

        if args[0] == 'w -s -h':
            with open('unittests/terminalsdump', 'r+b') as f:
                data = f.read()

        elif args[0] == 'finger p458749 -l -m':
            with open('unittests/fingerdump', 'r+b') as f:
                data = f.read()

        elif 'finger' in args[0]:
            data = b'finger: mysteryguest: no such user.'

        elif args[0].startswith('nvidia-smi'):
            data = b'123456\n123456\n'

        else:
            data = None

        return MockedCompletedProcess(stdout=data)

    def mocked_psutil_process_iter(*args, **kwargs):
        """
        """

        class MockedProc:
            class UID:
                def __init__(self, uid):
                    self.real = uid

            def __init__(self,
                         uid,
                         name='emacs',
                         username=None,
                         cpu_percent=10.0):
                self.uid = uid
                self.pid = 123456
                self._name = name
                self._cpu_percent = cpu_percent
                if username is None:
                    self._username = random.choice(['p', 's', 'f']) + ''.join(
                        [str(random.choice(range(9))) for _ in range(6)])
                else:
                    self._username = username

            def name(self):
                return self._name

            def username(self):
                return self._username

            def uids(self):
                return self.UID(self.uid)

            def cpu_percent(self):
                return self._cpu_percent

            def memory_percent(self):
                return 5.5

            def create_time(self):
                return time.time() - 5400

        for p in range(10):
            yield MockedProc(184444 + p)
        # A root user with way more cpu who should not be killed.
        yield MockedProc(
            1, name='root_stuff', username='root', cpu_percent=700.0)
        yield MockedProc(
            14584, name='dontkillme', username='duckling', cpu_percent=1800.0)
        yield MockedProc(
            14585, name='git', username='p987541', cpu_percent=1900.0)

    def mocked_terminate(*args, **kwargs):
        """
        """
        pass

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    def test_find_terminals(self, mock_run):
        terminals = kill_hogs.find_terminals_of_user('p945314')
        self.assertEqual(terminals, ['pts/1', 'pts/49'])

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    def test_send_message_to_terminals(self, mock_run):
        kill_hogs.send_message_to_terminals('p945314', 'hello, user')
        self.assertEqual(mock_run.call_count, 3)
        self.assertIn(
            mock.call('echo "hello, user" | write p945314 pts/49', shell=True),
            mock_run.call_args_list)

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    @mock.patch('kill_hogs.kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    def test_no_innocents_are_killed(self, mock_run, mock_terminate,
                                     mock_process_iter):
        kill_hogs.kill_hogs(
            config=self.config_dict, memory_threshold=10, cpu_threshold=600,
            gpu_max_walltime=120)
        self.assertFalse(mock_terminate.called)

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    @mock.patch('kill_hogs.kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    def test_violators_are_shot(self, mock_run, mock_terminate,
                                mock_process_iter):
        kill_hogs.kill_hogs(
            config=self.config_dict, memory_threshold=10, cpu_threshold=9.5,
            gpu_max_walltime=60)
        self.assertTrue(mock_terminate.called)

    def test_is_restricted(self):
        self.assertTrue(kill_hogs.is_restricted('p857496'))
        self.assertTrue(kill_hogs.is_restricted('s4579985'))
        self.assertFalse(kill_hogs.is_restricted('root'))

    @mock.patch('builtins.open', mock.mock_open(read_data=dummy_config))
    @mock.patch(
        'sys.argv',
        ['/opt/kill_hogs/kill_hogs.py', '--email', '--cpu_threshold', '9.0'])
    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    @mock.patch('kill_hogs.kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    @mock.patch('kill_hogs.kill_hogs.find_email', lambda x: 'test@acme.com')
    def test_main(self, mock_run, mock_terminate, mock_process_iter):
        with mailtest.Server() as mt:
            kill_hogs.main()
            self.assertEqual(len(mt.emails), 10)

    @mock.patch('builtins.open', mock.mock_open(read_data=dummy_config))
    @mock.patch('sys.argv', [
        '/opt/kill_hogs/kill_hogs.py', '--email', '--cpu_threshold', '9.0',
        '--request_only'
    ])
    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    @mock.patch('kill_hogs.kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    @mock.patch('kill_hogs.kill_hogs.find_email', lambda x: 'test@acme.com')
    def test_request_only(self, mock_run, mock_terminate, mock_process_iter):
        with mailtest.Server() as mt:
            kill_hogs.request_enforcement()
            kill_hogs.main()
            # check that 10 emails have been sent.
            self.assertEqual(len(mt.emails), 10)
            kill_hogs.main()
            # check that no more emails have been sent
            # as enforcement has not been requested.
            self.assertEqual(len(mt.emails), 10)

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    def test_find_email(self, mock_run):
        self.assertEqual(
            kill_hogs.find_email('p458749'), 'E.R.T.scrooge@rug.nl')

    def test_send_mail(self):
        with mailtest.Server() as mt:
            kill_hogs.send_mail(
                'root@exacluster', 'loue@institution.nl', 'abcde', port=1025)
            self.assertEqual(len(mt.emails), 1)


if __name__ == '__main__':
    unittest.main()
