#!/usr/bin/env python3

from collections import defaultdict
from pathlib import Path
import argparse
import json
import logging
import os
import psutil
import re
import requests
import smtplib
import subprocess
import time
import yaml

flagfile = '/tmp/kill_hogs_flagfile'

def post_to_slack(message: str, slack_url: str):
    """
    Post a message to slack.

    Args:
        message (str): Message to post
        slack_url (str): url to post message to
    """
    data = json.dumps({
        'channel': '#kill-hogs',
        'username': 'kill-hogs',
        'text': message,
        'icon_emoji': ':scales:'
    }).encode('utf-8')
    response = requests.post(
        slack_url, data=data, headers={'Content-Type': 'application/json'})
    logging.info('Posting to slack')
    logging.info(str(response.status_code) + str(response.text))


def request_enforcement():
    """
    Make a file in /tmp
    that wil signal the script to run.
    """
    Path(flagfile).touch()


def check_and_remove():
    """
    Deletete flag if it exists and return a bool whether it existed or not.
    Returns:
        True if flag exists
        False otherwise.
    """
    path = Path(flagfile)
    if path.exists():
        path.unlink()
        return True
    return False


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
    By default everybody except root is restricted. (this, of course, can be dangerous)

    Args:
        username (str): the username to test
        pattern (str): a regular expression to filter the users on.
    """
    return re.match(pattern, username) is not None


def procs_using_gpu():
    """
    Return which process IDs are using the GPU, based on the output of the nvidia-smi tool.
    """
    nvidia_smi = subprocess.run(
        'nvidia-smi --query-compute-apps=pid --format=csv,noheader',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    if nvidia_smi.returncode == 127:  # nvidia_smi not found.
        return []
    pids = [int(pid) for pid in nvidia_smi.stdout.decode('ascii').splitlines()]
    return pids


def kill_hogs(config: dict,
              memory_threshold,
              cpu_threshold,
              gpu_max_walltime: float = 1e9,
              dummy: bool = False,
              slack: bool = False,
              email: bool = False,
              request_only: bool = False,
              interval: float = .3):
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
    if request_only and not check_and_remove():
        logging.debug("Not enforcing since no flagfile is present.")
        return None
    else:
        logging.debug("enforcing...")

    users = defaultdict(lambda: {'cpu_percent': 0, 'memory_percent': 0, 'processes': [], 'gpu_walltime': 0})

    procs = list(psutil.process_iter())

    for proc in procs:
        try:
            proc.cpu_percent()
        except (psutil.NoSuchProcess, FileNotFoundError):
            pass

    gpu_pids = procs_using_gpu()

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
            if not is_restricted(username, config['user_pattern']):
                continue

            users[username]['memory_percent'] += proc.cached_memory_percent
            users[username]['cpu_percent'] += proc.cached_cpu_percent
            if gpu_max_walltime > 0 and proc.pid in gpu_pids:
                users[username]['gpu_walltime'] += (time.time() - proc.create_time()) / 60

            users[username]['processes'].append(proc)
        except (psutil.NoSuchProcess, FileNotFoundError):
            pass

    for username, data in users.items():
        if (data['memory_percent'] > memory_threshold
                or data['cpu_percent'] > cpu_threshold
                or data['gpu_walltime'] > gpu_max_walltime):
            # This process exceeds one or more limits and should be killed.
            message = [
                'User {} uses \n {:.2f} % of cpu. '.format(
                    username, data['cpu_percent']),
                '{:.2f} % of memory. '.format(data['memory_percent']),
                '{:.0f} minutes of GPU time'.format(data['gpu_walltime']),
                'The following processes will be killed:'
            ]
            for proc in data['processes']:
                try:
                    message.append(
                        '{} pid {} {} memory {:.2f}% cpu {:.2f}%'.format(
                            proc.username(), proc.pid, proc.name(),
                            proc.cached_memory_percent,
                            proc.cached_cpu_percent))
                except (psutil.NoSuchProcess, FileNotFoundError):
                    pass
            logging.info('\n'.join(message))

            if not dummy:
                send_message_to_terminals(proc.username(),
                                          config['terminal_warning'])
                if slack:
                    post_to_slack('\n'.join(message), config['slack_url'])

                if email:
                    email_address = find_email(proc.username())
                    if email_address is not None:
                        if request_only:
                            email_message = config['mail_body_request_only']
                        else:
                            email_message = config['mail_body']
                        email_message += '\n'.join(message)
                        send_mail(config['from_address'], email_address,
                                  email_message, config['mail_server_port'])

                terminate(data['processes'])


def find_email(username):
    """
    Return the email adress of <username> as reported by finger.

    Args:
      username (string): the username of the account.

    Returns:
      string: email adress or None

    """
    finger = subprocess.run(
        'finger {} -l -m'.format(username),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    try:
        data = finger.stdout.decode("utf-8").split('\n')
        # Basic check: exactly one `@` and at least one `.` after the `@`.
        match = re.search(r'(?<=Name: )[^@]+@[^@]+\.[^@]+$', data[0])
        return match.group(0)

    except IndexError:
        # a more explicit pass
        return None


def send_mail(sender: str, receiver: str, message: str, port: int = 25):
    """
    Send a message to a user whose processes have been killed.
    """

    message = f"""From: "(Kill Hogs)" <{sender}>
To: <{receiver}>
Subject: Processes killed.

{message}
    """

    try:
        smtpObj = smtplib.SMTP('localhost', port=port)
        smtpObj.sendmail(sender, [receiver], message)
        logging.info(f"Successfully sent email to {receiver}.")
    except Exception as e:
        logging.error(
            "Error: unable to send email.\nThe error was:\n{}".format(e))


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gpu_max_walltime",
        type=float,
        default=0,
        help="maximum wall time limit in minutes for using a gpu")
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
        "--cpu_interval",
        type=float,
        default=.3,
        help="Interval accross which to calculate cpu usage.")
    parser.add_argument(
        "--dummy",
        action='store_true',
        help="Only display what would be killed")
    parser.add_argument(
        "--email",
        action='store_true',
        help="Mail offenders when their processes are killed.")
    parser.add_argument(
        "--request_only",
        action='store_true',
        help="Only kill processes when a user has requested this.")
    parser.add_argument(
        "--slack", action='store_true', help="Post messages to slack")
    parser.add_argument(
        "--config_file",
        type=str,
        default='{}/.kill_hogs/kill_hogs.yml'.format(os.environ['HOME']),
        help="Config file, default: ~/.kill_hogs/kill_hogs.yml")
    args = parser.parse_args()

    with open(args.config_file, 'r') as f:
        config = yaml.load(f.read(), Loader=yaml.BaseLoader)

    kill_hogs(
        config=config,
        gpu_max_walltime=args.gpu_max_walltime,
        memory_threshold=args.memory_threshold,
        cpu_threshold=args.cpu_threshold,
        interval=args.cpu_interval,
        dummy=args.dummy,
        slack=args.slack,
        email=args.email,
        request_only=args.request_only)


if __name__ == '__main__':
    main()
