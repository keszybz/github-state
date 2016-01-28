#!/usr/bin/python3

from __future__ import print_function, division

import time
import requests
import pandas as pd
import logging
import os.path
import json

try:
    import http.client as http_client
except ImportError:
    # Python 2
    import httplib as http_client

# You must initialize logging, otherwise you'll not see debug output.
if False:
    http_client.HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

import matplotlib
if __name__ == '__main__':
    matplotlib.use('Agg')
from matplotlib import pyplot
matplotlib.style.use('ggplot')

def get_entries(url, max_pages=100, **params):
    params['per_page'] = 100
    for page in range(1, max_pages + 1): # for safety
        params['page'] = str(page)
        r = requests.get(url,
                         params=params,
                         auth=('user', 'DEADBEEF'))
        json = r.json()
        print('got {}, {} items'.format(url, len(json)))
        if not json:
            # empty list
            break
        yield json

def get_frames(url, **params):
    entries = get_entries(url, **params)
    total = sum(entries, [])
    return total

def get_issues_json(project, group, cache_time):
    fname = project.replace('/', '_') + '_' + group + '.json'
    try:
        ts = os.path.getmtime(fname)
        if ts + cache_time >= time.time():
            f = open(fname)
            return json.load(f)
    except (IOError, ValueError):
        pass

    url = 'https://api.github.com/repos/{}/{}'.format(project, group)
    raw = get_frames(url, state='all')
    f = open(fname, 'w')
    json.dump(raw, f)

    return raw

def get_issues(project='systemd/systemd', group='issues', cache_time=60*60):
    raw = get_issues_json(project, group, cache_time)

    df = pd.DataFrame(raw)
    df.set_index('number', inplace=True)
    df.sort_index(inplace=True)

    return df

def match_label(labels, jsonobj):
    names = {l['name'] for l in jsonobj}
    return bool(labels.intersection(names))

def filter_open_issues(issues, labels):
    open = issues[issues.state == 'open']
    filtered = open[[match_label(labels, jsonobj)
                     for jsonobj in open['labels']]]
    return filtered

def gb_sum(issues, attr):
    gb = issues['id'].groupby(pd.DatetimeIndex(issues[attr]).date).count()
    return gb.cumsum()

def massage(issues):
    closing = gb_sum(issues, 'closed_at')
    opening = gb_sum(issues, 'created_at')
    diff = opening - closing
    diff.fillna(method='pad', inplace=1)

    return opening, closing, diff

def do_plot(issues, title=None, extra_labels=None, extra_label=None):
    opening, closing, diff = massage(issues)
    f = pyplot.figure()
    ax = opening.plot(label='all')
    ax.set_ylabel('cumulative closed, cumulative all')
    closing.plot(label='closed')
    if title is not None:
        ax.set_title(title)
        f.canvas.set_window_title(title)
    f.autofmt_xdate()
    ax.legend(loc='upper left')

    ax2 = ax.twinx()
    ax2.set_ylabel('open', color='red')
    diff.plot(label='open', style='red')

    if extra_labels is not None:
        filtered = filter_open_issues(issues, extra_labels)
        filtered = gb_sum(filtered, 'created_at')
        filtered.plot(label=extra_label, style='maroon')

    ax2.legend(loc='lower right')

    return f

def small_plot(issues, title=None, style=None):
    opening, closing, diff = massage(issues)
    f = pyplot.figure(figsize=(2,1))
    ax = diff.plot(style=style)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.annotate(title, xy=(0, 1), xycoords='axes fraction', fontsize=16,
                horizontalalignment='left', verticalalignment='top')
    f.subplots_adjust(0, 0, 1, 1)
    return f

if __name__ == '__main__':
    issues = get_issues(group='issues')
    has_pr = -issues.pull_request.isnull()
    pulls = issues[has_pr]
    other = issues[-has_pr]

    f = do_plot(other, 'Issues',
                extra_labels={'needs-reporter-feedback'},
                extra_label='postponed')
    f2 = do_plot(pulls, 'Pull requests',
                 extra_labels={'postponed',
                               'reviewed/needs-rework',
                               'needs-reporter-feedback'},
                 extra_label='postponed')
    f.savefig('images/systemd-issues.svg')
    f.savefig('images/systemd-issues.png')
    f2.savefig('images/systemd-pull-requests.svg')
    f2.savefig('images/systemd-pull-requests.png')

    f3 = small_plot(other, title='Issues', style='red')
    f4 = small_plot(pulls, title='Pull requests', style='green')

    f3.savefig('images/systemd-issues-small.svg')
    f3.savefig('images/systemd-issues-small.png')
    f4.savefig('images/systemd-pull-requests-small.svg')
    f4.savefig('images/systemd-pull-requests-small.png')
