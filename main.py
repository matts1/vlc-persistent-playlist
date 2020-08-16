import os
import sys
import time
import traceback
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

from torrent import select_torrent

VIDEO_FORMATS = ["mkv", "mp4"]

def run(url, **params):
    url = f'http://localhost:8080/requests/{url}.xml?{"&".join(k + "=" + str(v) for k, v in params.items())}'
    response = requests.get(
            url,
            auth=HTTPBasicAuth('', 'pass'))
    assert response.status_code == 200
    return ET.fromstring(response.content)

def status(command=None, **params):
    if command is not None:
        params['command'] = command
    return run('status', **params)

def error(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    time.sleep(10)
    exit(1)

def main():
    if len(sys.argv) < 2:
        root_dir = open('H:/unwatched/.recent').read()
    elif sys.argv[1] == "--":
        root_dir = input("Enter the absolute path to the directory: ")
    elif sys.argv[1] == "--torrent":
        root_dir = select_torrent()
    else:
        root_dir = sys.argv[1]

    os.startfile(r"C:\Program Files\VideoLAN\VLC\vlc.exe")

    if not os.path.exists(root_dir):
        error("Directory doesn't exist:", root_dir)

    with open('H:/unwatched/.recent', 'w') as f:
        f.write(root_dir)

    playlist_path = os.path.join(root_dir, '.playlist')

    status('pl_empty')  # Clear the playlist
    for root, _, files in os.walk(root_dir):
        for f in files:
            path = os.path.join(root, f)
            ext = os.path.splitext(path)
            if ext[1].lstrip(".") in VIDEO_FORMATS:
                print(path)
                status('in_enqueue', input=path)

    if os.path.exists(playlist_path):
        with open(playlist_path, 'r') as f:
            data = f.read().rsplit(",", 1)
            if len(data) != 2:
                error(f"Invalid playlist: '{data}'")
            playlist_upto_file, seconds = data
    else:
        playlist_upto_file = None
        seconds = 0

    for item in run('playlist').iter('leaf'):
        if item.attrib['uri'] == playlist_upto_file or playlist_upto_file is None:
            print("seeking to file", item.attrib['uri'])
            status('pl_play', id=item.attrib['id'])
            break
    print("Seeking to time", seconds)
    status('seek', val=seconds)

    while True:
        # Save where you're up to
        seconds = int(status().find('time').text)
        for i, item in enumerate(run('playlist').iter('leaf')):
            if 'current' in item.attrib:
                playlist_upto = item.attrib['uri']
        with open(playlist_path, 'w') as f:
            f.write(f"{playlist_upto},{seconds}")
        time.sleep(10)

try:
    main()
except Exception:
    error("".join(traceback.format_exception(*sys.exc_info())))
