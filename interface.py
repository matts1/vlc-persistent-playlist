import itertools
import os
import urllib

import psutil
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from urllib.parse import urlencode


def run(url, **params):
    # urlencode double escapes some characters
    url = f'http://localhost:8080/requests/{url}.xml?{"&".join(k + "=" + str(v).replace("&", "%26") for k, v in params.items())}'
    response = requests.get(
            url,
            auth=HTTPBasicAuth('', 'pass'))
    assert response.status_code == 200
    return ET.fromstring(response.content)


def status(command=None, **params):
    if command is not None:
        params['command'] = command
    return run('status', **params)


def maybe_start_process(path):
    basename = os.path.basename(path)
    for process in psutil.process_iter():
        try:
            if process.exe() == path:
                print(basename, "already started")
                return
        except psutil.AccessDenied:
            pass
    print("Starting", basename)
    os.startfile(path)


def playlist():
    pl = {}
    current = None
    for item in run('playlist').iter('leaf'):
        path = urllib.parse.unquote(item.attrib['uri'])
        assert path.startswith("file:///")
        path = os.path.normpath(path[8:])
        pl[path] = item.attrib['id']
        if 'current' in item.attrib:
            current = path
    return pl, current
