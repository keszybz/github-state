# github-state
A script to pull the list of issues from github and generate plots with statistics

### Example invocation
```
python3 github_state.py --project matplotlib/matplotlib \
     --auth user:hexadecimal-auth-token \
     --plot1-filter=needs-reporter-feedback \
     --plot2-filter=postponed,reviewed/needs-rework,needs-reporter-feedback
```

This will generate some plots in images/.                                           
The module can also be imported interactively.                                      

<img src="doc/images/systemd-systemd-issues.png" width="50%" />
<img src="doc/images/systemd-systemd-pull-requests.png" width="50%" />

### License

This script is licensed under the GNU Lesser General Public License, version 2.1 or later, at your option.
