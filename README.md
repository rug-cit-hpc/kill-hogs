# Kill hogs

We at team HPC of the university of Groningen run job schedueling clusters.
Some users are running their programs on the login node of these clusters instead of submitting jobs. This leads to a high load on the login node, which leads to unhappy users who are unable to submit jobs.
"kill hogs" is a crude attempt at mittigating these problems. It is a cronjob that checks the resources (cpu and ram) that are used by each user. If they reach a certain treshold, all the user's processes above a minimum treshold are killed. 
The user is informed of this via a message in the terminal.
A message is also send to slack to inform us.


**this program might kill processes you don't want killed and lock you out**


## Installation.

We install the cronjob via ansible.

`ansible 
