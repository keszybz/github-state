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

import http.client as http_client

Auth = collections.namedtuple('Auth', 'user auth')
def colon_seperated_pair(arg):
    pair = arg.split(':', 1)
    if len(pair) == 1:
        return Auth(pair[0], '')
    else:
        return Auth(*pair)

def comma_seperated_list(arg):
    return arg.split(',')

class PlotConfig:
    def __init__(self, string):
        parts = string.split(':')
        if len(parts) > 2:
            raise ValueError('plot syntax is: [title:]issue[,issue...]')

        if len(parts) > 1:
            self.title = parts[0]
            self.labels = comma_seperated_list(parts[1])
        else:
            self.labels = comma_seperated_list(parts[0])

    @classmethod
    def make(cls, default_title, *, pulls=False, small=False):
        _pulls = pulls
        _small = small
        class TitledPlot(cls):
            title = default_title
            pulls = _pulls
            small = _small
        return TitledPlot

def parser():
    parser = configargparse.ArgParser()
    parser.add_argument('--project', required=True,
                        help='GitHub project, specified as USER/REPO')
    parser.add_argument('--auth', type=colon_seperated_pair, required=True,
                        help='GitHub API token, specified as user/digits')
    parser.add_argument('--cache-time', type=float, default=60*60,
                        help='How often should the issue list be refreshed')

    parser.add_argument('--issues', dest='plots', action='append',
                        nargs='?', const='Issues',
                        metavar='PLOT_CONFIG',
                        type=PlotConfig.make('Issues'),
                        help='Add a plot of open and closed issues')
    parser.add_argument('--pull-requests', dest='plots', action='append',
                        nargs='?', const='Pull requests',
                        metavar='PLOT_CONFIG',
                        type=PlotConfig.make('Pull requests', pulls=True),
                        help='Add a plot of open and closed pull requests')
    parser.add_argument('--issues-small', dest='plots', action='append',
                        nargs='?', const='Issues',
                        metavar='PLOT_CONFIG',
                        type=PlotConfig.make('Issues', small=True),
                        help='Add a thumbnail plot of open and closed issues')
    parser.add_argument('--pull-requests-small', dest='plots', action='append',
                        nargs='?', const='Pull requests',
                        metavar='PLOT_CONFIG',
                        type=PlotConfig.make('Pull requests', pulls=True, small=True),
                        help='Add a thumbnail plot of open and closed pull requests')

    parser.add_argument('--formats', type=comma_seperated_list, default=['svg', 'png'],
                        help='Write images in each of those formats')
    parser.add_argument('--debug', action='store_true',
                        help='Turn on debugging of the network operations')

    parser.add_argument('config', is_config_file=True, nargs='?',
                        default='project.conf',
                        help='Read config from this file')

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
        r.raise_for_status()
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
    labels = set(labels)
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

def do_plot(plot_config, issues):
    opening, closing, diff = massage(issues)
    f = pyplot.figure()
    ax = opening.plot(label='all')
    ax.set_ylabel('cumulative closed, cumulative all')
    closing.plot(label='closed')
    ax.set_title(plot_config.title)
    f.canvas.set_window_title(plot_config.title)
    f.autofmt_xdate()
    ax.legend(loc='upper left')

    ax2 = ax.twinx()
    ax2.set_ylabel('open', color='red')
    diff.plot(label='open', style='red')

    if plot_config.labels:
        filtered = filter_open_issues(issues, plot_config.labels)
        if filtered.size > 0:
            filtered = gb_sum(filtered, 'created_at')
        else:
            filtered = diff.copy()
            filtered[:] = 0
        filtered.plot(label=plot_config.labels[0], style='maroon')

    ax2.legend(loc='lower right')

    return f

def do_small_plot(plot_config, issues):
    opening, closing, diff = massage(issues)
    f = pyplot.figure(figsize=(2,1))
    ax = diff.plot() # style=style)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.annotate(plot_config.title,
                xy=(0, 1), xycoords='axes fraction', fontsize=16,
                horizontalalignment='left', verticalalignment='top')
    f.subplots_adjust(0, 0, 1, 1)
    return f

def image_filename(config, plot_config, ext):
    prefix = config.project.replace('/', '-')
    subj = plot_config.title.lower().replace(' ', '-')
    small = '-small' if plot_config.small else ''
    return 'images/{}-{}{}.{}'.format(prefix, subj, small, ext)

def savefig(config, plot_config, figure):
    try:
        os.mkdir('images')
    except FileExistsError:
        pass
    for extension in config.formats:
        fname = image_filename(config, plot_config, extension)
        figure.savefig(fname)
        if config.debug:
            print('Saved {}'.format(fname))

def issues_and_prs(config):
    issues = get_issues(config, group='issues')
    has_pr = -issues.pull_request.isnull()
    pulls = issues[has_pr]
    other = issues[-has_pr]
    return other, pulls

if __name__ == '__main__':
    config = parser().parse_args()
    if config.debug:
        init_logging()

    issues, pulls = issues_and_prs(config)

    for plot_config in config.plots:
        items = pulls if plot_config.pulls else issues
        if plot_config.small:
            f = do_small_plot(plot_config, items)
        else:
            f = do_plot(plot_config, items)
        savefig(config, plot_config, f)
