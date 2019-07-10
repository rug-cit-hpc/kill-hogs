from unittest import mock
import kill_hogs
import random
import unittest


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
        kill_hogs.post_to_slack('Hello world', slack_url='https://hooks.slack.com/services/some/random/string')

        # assert that our mocked function was called with the right parameters
        self.assertIn(
            mock.call(
                'https://hooks.slack.com/services/some/random/string',
                data=b'{"channel": "#peregrine-alerts", '
                b'"username": "kill-hogs", "text": "Hello world", '
                b'"icon_emoji": ":scales:"}',
                headers={'Content-Type': 'application/json'}),
            mock_get.call_args_list)


class KillhogsTestCase(unittest.TestCase):

    user_pattern = '^((s|p|f)[0-9]{5,7}|umcg-[a-z]{3,10})'

    def mocked_subprocess_run(*args, **kwargs):
        """
        """

        class MockedCompletedProcess:
            def __init__(self, stdout, stderr=None):
                self.stdout = stdout
                self.stderr = stderr

        if args[0] == 'w -s -h':
            with open('unittests/terminalsdump', 'r+b') as f:
                data = f.read()
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

        for p in range(10):
            yield MockedProc(184444 + p)
        # A root user with way more cpu who should not be killed.
        yield MockedProc(
            1, name='root_stuff', username='root', cpu_percent=700.0)
        yield MockedProc(
            14584, name='dontkillme', username='duckling', cpu_percent=1800.0)

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
    @mock.patch('kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    def test_no_innocents_are_killed(self, mock_run, mock_terminate,
                                     mock_process_iter):
        kill_hogs.kill_hogs(memory_threshold=10, cpu_threshold=600, user_pattern=self.user_pattern)
        self.assertFalse(mock_terminate.called)

    @mock.patch('subprocess.run', side_effect=mocked_subprocess_run)
    @mock.patch('kill_hogs.terminate', side_effect=mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=mocked_psutil_process_iter)
    def test_violators_are_shot(self, mock_run, mock_terminate,
                                mock_process_iter):
        kill_hogs.kill_hogs(memory_threshold=10, cpu_threshold=9.5, user_pattern=self.user_pattern)
        self.assertTrue(mock_terminate.called)

    def test_is_restricted(self):
        self.assertTrue(kill_hogs.is_restricted('p857496'))
        self.assertTrue(kill_hogs.is_restricted('s4579985'))
        self.assertFalse(kill_hogs.is_restricted('root'))


class MainTestCase(unittest.TestCase):
    dummy_config = '''
---
slack_url: 'https://hooks.slack.com/services/some/random/string'
user_pattern: '^((s|p|f)[0-9]{5,7}|umcg-[a-z]{3,10})'
'''

    @mock.patch('builtins.open', mock.mock_open(read_data=dummy_config))
    @mock.patch('sys.argv', ['/opt/kill_hogs/kill_hogs.py'])
    @mock.patch('subprocess.run', side_effect=KillhogsTestCase.mocked_subprocess_run)
    @mock.patch('kill_hogs.terminate', side_effect=KillhogsTestCase.mocked_terminate)
    @mock.patch('psutil.process_iter', side_effect=KillhogsTestCase.mocked_psutil_process_iter)
    def test_main(self, mock_run, mock_terminate, mock_process_iter):
        kill_hogs.main()


if __name__ == '__main__':
    unittest.main()
