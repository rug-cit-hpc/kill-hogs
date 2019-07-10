#! /usr/bin/env/python3

from string import digits
import random
import re
import sys


class RandomAccountDict(dict):
    def __missing__(self, key):
        if 'umcg' in key:
            value = 'umcg-' + random.choice(
                ['huey', 'dewey', 'louie', 'daisy'])
        else:
            value = key[0] + ''.join([random.choice(digits) for d in key[1:]])

        self[key] = value
        return value


if __name__ == '__main__':
    new_number = RandomAccountDict()

    out = []

    with open(sys.argv[1], 'r') as f:
        for line in f:
            match = re.match('^((s|p|f)[0-9]{5,7}|umcg-[a-z]{3,10})', line)

            if match:
                out.append(
                    re.sub('%s[a-z]{0,5}' % match.group(0),
                           new_number[match.group(0)], line))
            else:
                out.append(line)
    print(''.join(out))
