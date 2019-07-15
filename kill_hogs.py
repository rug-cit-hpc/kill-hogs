#!/usr/bin/env python3

from collections import defaultdict
import argparse
import json
import logging
import psutil
import re
import requests
import subprocess
import time
import yaml


def post_to_slack(message: str, slack_url: str):
    """
    Post a message to slack.

    Args:
        message (str): Message to post
        slack_url (str): url to post message to
    """
    data = json.dumps({
        'channel': '#peregrine-alerts',
        'username': 'kill-hogs',
        'text': message,
        'icon_emoji': ':scales:'
    }).encode('utf-8')
    response = requests.post(
        slack_url, data=data, headers={'Content-Type': 'application/json'})
    logging.info('Posting to slack')
    logging.info(str(response.status_code) + str(response.text))


def send_message_to_terminals(user: str, message: str):
    """
    Sends <message> to all terminals on which <user> is logged in.
    """
    terminals = find_terminals_of_user(user)
    for terminal in terminals:
        subprocess.run(
            'echo "{message}" | write {user} {terminal}'.format(
                message=message, user=user, terminal=terminal),
            shell=True)


def find_terminals_of_user(user: str):
    """
    Args:
        user (str): The user who's terminals to return.
    Returns:
        list: A list of terminals (string)
    """
    terminals = subprocess.run(
        'w -s -h', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [
        t.split()[1]
        for t in str(terminals.stdout).strip('b\'').strip('').split('\\n')
        if user in t
    ]


def on_terminate(proc):
    """
    Callback for terminate()
    """
    logging.info('process {} terminated with exit code {}'.format(
        proc, proc.returncode))


def terminate(kill_list):
    """
    Terminate processes. Kill if terminate is unsuccesful.

    Args:
        kill_list (list): List of processes to kill.
    """
    for proc in kill_list:
        proc.terminate()
    gone, alive = psutil.wait_procs(
        kill_list, timeout=3, callback=on_terminate)
    for proc in alive:
        logging.info('Killing {} with signal 9'.format(proc))
        proc.kill()


def is_restricted(username: str, pattern: str = '^(?!root).*'):
    """
    Test if processes of username should be limited in their resources.
    Bu default everybody except root is restricted. (this, of course, can be dangerous)

    Args:
        username (str): the username to test
        pattern (str): a regular expression to filter the users on.
    """
    return re.match(pattern, username) is not None


def kill_hogs(memory_threshold,
              cpu_threshold,
              dummy: bool = False,
              slack: bool = False,
              slack_url = None,
              interval: float = .3,
              warning: str = '',
              user_pattern = None):
    """
    Kill all processes of a user using more than <threshold> % of memory. And cpu.
    For efficiency reasons only processes using more than .1 % of the available
    resources are counted.

    Args:
        memory_threshold (float): Percentage of user resources above which to kill.
        cpu_threshold (float): Percentage of user resources above which to kill.
        dummy (bool): If true, do not actually kill processes.
        slack (bool): send messages to slack.
    """
    users = defaultdict(lambda: {'cpu_percent': 0, 'memory_percent': 0, 'processes': []})

    procs = list(psutil.process_iter())

    for proc in procs:
        try:
            proc.cpu_percent()
        except (psutil.NoSuchProcess, FileNotFoundError):
            pass

    time.sleep(interval)
    for proc in procs:
        try:
            # First call of cpu_percent() without blocking interval is meaningless.
            # see https://psutil.readthedocs.io/en/latest/
            proc.cached_cpu_percent = proc.cpu_percent()
            proc.cached_memory_percent = proc.memory_percent()

            if proc.uids().real == 0 or (proc.cached_memory_percent < .1
                                         and proc.cached_cpu_percent < 1):
                continue  # do not kill root processes.
            # Check username here. It is somewhat expensive.
            username = proc.username()
            if not is_restricted(username, user_pattern):
                continue

            users[username]['memory_percent'] += proc.cached_memory_percent
            users[username]['cpu_percent'] += proc.cached_cpu_percent

            users[username]['processes'].append(proc)
        except (psutil.NoSuchProcess, FileNotFoundError) as e:
            pass

    for username, data in users.items():
        if data['memory_percent'] > memory_threshold or data['cpu_percent'] > cpu_threshold:
            message = [
                'User {} uses \n {:.2f} % of cpu. '.format(
                    username, data['cpu_percent']),
                '{:.2f} % of memory. '.format(data['memory_percent']),
                'The following processes will be killed:'
            ]
            for proc in data['processes']:
                try:
                    message.append(
                     '{} pid {} {} memory {:.2f}% cpu {:.2f}%'.format(
                        proc.username(), proc.pid, proc.name(),
                        proc.cached_memory_percent, proc.cached_cpu_percent))
                except (psutil.NoSuchProcess, FileNotFoundError) as e:
                    pass
            logging.info('\n'.join(message))
            if warning == '':
                warning = """Please submit your processes as a job.
Your processes have been killed and this incident has been reported.
For more information, see https://redmine.hpc.rug.nl/redmine/projects/peregrine/wiki/FAQ"""
            send_message_to_terminals(proc.username(), warning)
            if slack:
                post_to_slack('\n'.join(message), slack_url)
            if not dummy:
                terminate(data['processes'])


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--memory_threshold",
        type=float,
        default=10,
        help="memory percentage above which processes are killed")
    parser.add_argument(
        "--cpu_threshold",
        type=float,
        default=600,
        help="cpu percentage above which processes are killed")
    parser.add_argument(
        "--dummy",
        action='store_true',
        help="Only display what would be killed")
    parser.add_argument(
        "--slack", action='store_true', help="Post messages to slack")
    args = parser.parse_args()

    with open('/opt/kill_hogs/kill_hogs.yml', 'r') as f:
        config = yaml.load(f.read(), Loader=yaml.BaseLoader)
    slack_url = config['slack_url']
    user_pattern = config['user_pattern']

    kill_hogs(
        memory_threshold=args.memory_threshold,
        cpu_threshold=args.cpu_threshold,
        dummy=args.dummy,
        slack=args.slack,
        slack_url=slack_url,
        user_pattern=user_pattern)


if __name__ == '__main__':
    main()
