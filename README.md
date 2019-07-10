# Kill hogs

We at team HPC of the university of Groningen run job schedueling clusters.
Some users are running their programs on the login node of these clusters instead of submitting jobs. This leads to a high load on the login node, which leads to unhappy users who are unable to submit jobs.
"kill hogs" is a crude attempt at mittigating these problems. It is a cronjob that checks the resources (cpu and ram) that are used by each user. If they reach a certain treshold, all the user's processes above a minimum treshold are killed. 
The user is informed of this via a message in the terminal.
A message is also send to slack to inform us.


**this program might kill processes you don't want killed and lock you out**


## Installation.

We install the cronjob via ansible on a centos7 host instead of installing the requirements with pip, we opt for the following yum packages.

- python36-requests
- python36-psutil

The cronjob looks like this:

```cronjob
*/2 * * * * root /usr/bin/python36 /opt/kill_hoggs/kill_hoggs.py --slack
```


## Run tests

```python

python -m unittest unittests.test_kill_hogs


# Or if you want coverage information.

coverage run -m unittest unittests.test_kill_hogs
coverage report -m kill_hogs.py
```


