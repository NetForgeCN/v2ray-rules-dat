#!/usr/bin/env python3

import sys

""" Find redundant items in domain lists.
    e.g. 'bar.foo.com' is redundant for 'foo.com'.
"""

def load(list):
    results = []
    with open(list, 'r') as f:
        for line in f.readlines():
            line = line.strip()
            if line == '' or line.startswith('#'):
                continue
            domain_labels = line.lower().split('.')
            results.append(domain_labels)
    results.sort(key=len)
    return results

def find(labelses, removedDomainFile):
    tree = {}
    LEAF = 1
    for labels in labelses:
        domain = '.'.join(labels)
        node = tree
        while len(labels) > 0:
            label = labels.pop()
            if label in node:
                if node[label] == LEAF:
                    with open(removedDomainFile, "a") as f:
                        f.write(domain)
                        f.write("\n")
                    break
            else:
                if len(labels) == 0:
                    node[label] = LEAF
                else:
                    node[label] = {}
            node = node[label]

if __name__ == '__main__':
    find(load(sys.argv[1]), sys.argv[2])
