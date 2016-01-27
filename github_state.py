#!/usr/bin/python3

from __future__ import print_function, division

import requests
import pandas as pd
import matplotlib
if __name__ == '__main__':
    matplotlib.use('svg')
from matplotlib import pyplot

def get_entries(url, max_pages=20, **params):
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

def get_frame(url, **params):
    entries = get_entries(url, **params)
    json = sum(entries, [])
    df = pd.DataFrame(json)
    df.sort_values('created_at', inplace=True)
    return df

def get_issues(project='systemd/systemd', group='issues'):
    url = 'https://api.github.com/repos/{}/{}'.format(project, group)
    df1 = get_frame(url, state='open')
    df2 = get_frame(url, state='closed')
    return pd.concat([df1, df2])

def massage(issues):
    closing = issues['number'].groupby(pd.DatetimeIndex(issues.closed_at).date).count()
    opening = issues['number'].groupby(pd.DatetimeIndex(issues.created_at).date).count()
    opening = opening.cumsum()
    closing = closing.cumsum()
    diff = opening - closing
    diff.fillna(method='pad', inplace=1)
    return opening, closing, diff

def do_plot(issues, title=None):
    opening, closing, diff = massage(issues)
    f = pyplot.figure()
    ax = opening.plot()
    ax.set_ylabel('cumulative closed, cumulative all')
    closing.plot()
    if title is not None:
        ax.set_title(title)
        f.canvas.set_window_title(title)
    f.autofmt_xdate()
    ax2 = ax.twinx()
    ax2.set_ylabel('open', color='red')
    diff.plot(style='red')
    return f

if __name__ == '__main__':
    issues = get_issues(group='issues')
    pulls = get_issues(group='pulls')
    f = do_plot(issues, 'Issues')
    f2 = do_plot(pulls, 'Pull requests')
    f.savefig('systemd-issues.svg')
    f2.savefig('systemd-pull-requests.svg')
