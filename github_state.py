#!/usr/bin/python3

from __future__ import print_function, division

import time
import requests
import pandas as pd
import logging
import os.path
import json
import configargparse
import collections

try:
    import http.client as http_client
except ImportError:
    # Python 2
    import httplib as http_client

Auth = collections.namedtuple('Auth', 'user auth')
def colon_seperated_pair(arg):
    pair = arg.split(':', 1)
    if len(pair) == 1:
        return Auth(pair[0], '')
    else:
        return Auth(*pair)

def comma_seperated_list(arg):
    return arg.split(',')

def parser():
    parser = configargparse.ArgParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--auth', type=colon_seperated_pair, required=True)
    parser.add_argument('--cache-time', type=float, default=60*60)

    parser.add_argument('--plot1-filter', type=comma_seperated_list)
    parser.add_argument('--plot2-filter', type=comma_seperated_list)

    parser.add_argument('--debug', action='store_true')

    parser.add_argument('config', is_config_file=True, nargs='+')

    return parser

# You can initialize logging to see debug output
def init_logging():
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

def get_entries(config, url, max_pages=100, **params):
    params['per_page'] = 100
    for page in range(1, max_pages + 1): # for safety
        params['page'] = str(page)
        r = requests.get(url,
                         params=params,
                         auth=config.auth)
        json = r.json()
        print('got {}, {} items'.format(url, len(json)))
        if not json:
            # empty list
            break
        yield json

def get_frames(config, url, **params):
    entries = get_entries(config, url, **params)
    total = sum(entries, [])
    return total

def get_issues_json(config, group):
    fname = config.project.replace('/', '_') + '_' + group + '.json'
    try:
        ts = os.path.getmtime(fname)
        if ts + config.cache_time >= time.time():
            f = open(fname)
            return json.load(f)
    except (IOError, ValueError):
        pass

    url = 'https://api.github.com/repos/{}/{}'.format(config.project, group)
    raw = get_frames(config, url, state='all')
    f = open(fname, 'w')
    json.dump(raw, f)

    return raw

def get_issues(config, group='issues'):
    raw = get_issues_json(config, group)

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

def image_file(config, subj, ext):
    prefix = config.project.replace('/', '-')
    return 'images/{}-{}.{}'.format(prefix, subj, ext)

if __name__ == '__main__':
    config = parser().parse_args()
    if config.debug:
        init_logging()

    issues = get_issues(config, group='issues')
    has_pr = -issues.pull_request.isnull()
    pulls = issues[has_pr]
    other = issues[-has_pr]

    f = do_plot(other, 'Issues',
                extra_labels=set(config.plot1_filter),
                extra_label=config.plot1_filter[0])
    f2 = do_plot(pulls, 'Pull requests',
                 extra_labels=set(config.plot2_filter),
                 extra_label=config.plot2_filter[0])
    f.savefig(image_file(config, 'issues', 'svg'))
    f.savefig(image_file(config, 'issues', 'png'))
    f2.savefig(image_file(config, 'pull-requests', 'svg'))
    f2.savefig(image_file(config, 'pull-requests', 'png'))

    f3 = small_plot(other, title='Issues', style='red')
    f4 = small_plot(pulls, title='Pull requests', style='green')

    f3.savefig(image_file(config, 'issues-small', 'svg'))
    f3.savefig(image_file(config, 'issues-small', 'png'))
    f4.savefig(image_file(config, 'pull-requests-small', 'svg'))
    f4.savefig(image_file(config, 'pull-requests-small', 'png'))
