#!/usr/bin/python3

from __future__ import print_function, division

import time
import requests
import pandas as pd
import numpy as np
import logging
import os.path
import argparse
import configparser
import json
import collections

import http.client as http_client

import matplotlib
if __name__ == '__main__':
    matplotlib.use('Agg')
from matplotlib import pyplot
matplotlib.style.use('ggplot')


Auth = collections.namedtuple('Auth', 'user auth')
def colon_separated_pair(arg):
    pair = arg.split(':', 1)
    if len(pair) == 1:
        return Auth(pair[0], '')
    else:
        return Auth(*pair)

def comma_separated_list(arg):
    ll = arg.split(',')
    if ll == ['']:
        return []
    return [item.strip() for item in ll]

class PlotConfig:
    def __init__(self, type, title, labels, small=False):
        assert type in {'pulls', 'issues'}
        self.type = type
        self.title = title
        self.labels = labels
        self.small = small

    def __str__(self):
        return '{} plot \"{}\" [{}]{}'.format(self.type,
                                              self.title,
                                              ','.join(self.labels),
                                              ' small' if self.small else '')
def parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project',
                        help='GitHub project, specified as USER/REPO')
    parser.add_argument('--auth', type=colon_separated_pair,
                        help='GitHub API token, specified as user/digits')
    parser.add_argument('--cache-time', type=float, default=60*60,
                        help='How often should the issue list be refreshed')
    parser.add_argument('--formats', type=comma_separated_list, default=['svg', 'png'],
                        help='Write images in each of those formats')
    parser.add_argument('--debug', action='store_true',
                        help='Turn on debugging of the network operations')
    parser.add_argument('dir',
                        help='Operate on this directory')
    return parser

def update_config_entry(args, config, args_name, section, config_name, type=str):
    if getattr(args, args_name) is not None:
        return
    try:
        val = config[section][config_name]
    except Exception:
        return
    setattr(args, args_name, type(val))

def update_config(args, conffile):
    config = configparser.ConfigParser()
    foo = config.read(conffile)
    if not foo:
        raise ValueError('Unable to read config file "{}"'.format(conffile))
    update_config_entry(args, config, 'project', 'project', 'project')
    update_config_entry(args, config, 'auth', 'project', 'auth', colon_separated_pair)

    if args.project is None:
        raise ValueError('project must be specified')
    if args.auth is None:
        raise ValueError('auth must be specified')

    args.plots = []

    # each section, except 'project', is a plot
    for secname, section in config.items():
        if secname in {'project', 'DEFAULT'}:
            continue

        type = section.get('type') or None
        if type is None:
            if 'issue' in secname.lower():
                type = 'issues'
            elif 'pull' in secname.lower():
                type = 'pulls'
            else:
                raise ValueError('need to specify type= in section [{}]'.format(secname))

        labels = section.get('labels') or ''
        labels = comma_separated_list(labels)

        small = section.get('small')
        small = small == '1'

        args.plots.append(PlotConfig(type, secname, labels=labels))
        if small:
            args.plots.append(PlotConfig(type, secname, labels=labels, small=True))

# You can initialize logging to see debug output
def init_logging():
    http_client.HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

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
    fname = os.path.join(config.dir,
                         config.project.replace('/', '_') + '_' + group + '.json')
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

def do_label_plot(plot_config, issues):
    f = pyplot.figure()
    f.canvas.set_window_title(plot_config.title)
    ax = f.gca()
    ax.set_title(plot_config.title)

    opening, closing, diff = massage(issues)

    base = diff * 0
    series = collections.OrderedDict(_base=base)

    for label in plot_config.labels:
        filtered = filter_open_issues(issues, [label])
        if filtered.size == 0:
            continue
        filtered = gb_sum(filtered, 'created_at')
        series[label] = filtered

    df = pd.DataFrame(series)
    df.fillna(method='ffill', inplace=True)
    df.fillna(0, inplace=True)

    for label in df.columns:
        if label == '_base':
            continue
        top = base + df[label]
        ax.fill_between(base.index.values, base.values, top.values,
                        label='label:' + label)
        base = top

    # diff.plot() messes up the order
    ax.plot(diff.index.values, diff.values, label='open', color='red')
    ax.set_xlim(diff.index.values.min(), diff.index.values.max())
    ax.set_ylim(-1)

    ax.legend(loc='upper left')
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[:1] + handles[:0:-1], labels[:1] + labels[:0:-1])

    f.autofmt_xdate()
    f.tight_layout()
    return f

def do_plot(plot_config, issues):
    f = pyplot.figure()
    opening, closing, diff = massage(issues)
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
    prefix = os.path.join(config.dir, 'images', config.project.replace('/', '-'))
    subj = plot_config.title.lower().replace(' ', '-')
    small = '-small' if plot_config.small else ''
    return '{}-{}{}.{}'.format(prefix, subj, small, ext)

def savefig(config, plot_config, figure):
    for extension in config.formats:
        fname = image_filename(config, plot_config, extension)
        os.makedirs(os.path.basename(fname), exist_ok=True)
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
    args = parser().parse_args()
    if args.debug:
        init_logging()

    update_config(args, os.path.join(args.dir, 'project.conf'))

    issues, pulls = issues_and_prs(args)

    for plot in args.plots:
        if args.debug:
            print(str(plot))

        items = pulls if plot.type == 'pulls' else issues
        if plot.small:
            f = do_small_plot(plot, items)
        elif plot.labels:
            f = do_label_plot(plot, items)
        else:
            f = do_plot(plot, items)
        savefig(args, plot, f)
