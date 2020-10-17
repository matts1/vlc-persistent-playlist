import copy
import json
import os
import re
import sys
import threading
import time
import traceback
import xml.etree.ElementTree as ET

import psutil as psutil
import requests
from requests.auth import HTTPBasicAuth

from speech import get_rewritten_line
from torrent import select_torrent

GLOBAL_LAST_UNDO = 'last_undo'

KEY_PLAYLIST = 'playlist_upto'
KEY_TIME = 'time'
KEY_AUDIO = 'audio'
KEY_SUBS = 'subs'
VALID_MANUAL_KEYS = {KEY_AUDIO, KEY_SUBS}

VIDEO_FORMATS = ["mkv", "mp4"]

global_vars = {}

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

def seek(seconds):
    print("Seeking to time", seconds)
    return status('seek', val=seconds)

def error(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    time.sleep(10)
    exit(1)

def track(kind, matches):
    for i in range(matches):
      status('key', val=kind)

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

def main():
    if len(sys.argv) < 2:
        root_dir = open('H:/unwatched/.recent').read()
    elif sys.argv[1] == "--":
        root_dir = input("Enter the absolute path to the directory: ")
    elif sys.argv[1] == "--torrent":
        root_dir = select_torrent()
    else:
        root_dir = sys.argv[1]

    maybe_start_process("C:\Program Files (x86)\VMR Connect\VMRHub.exe")
    time.sleep(1)
    maybe_start_process(r"C:\Program Files\VideoLAN\VLC\vlc.exe")

    if not os.path.exists(root_dir):
        error("Directory doesn't exist:", root_dir)

    with open('H:/unwatched/.recent', 'w') as f:
        f.write(root_dir)

    playlist_path = os.path.join(root_dir, '.playlist.json')
    config_path = os.path.join(root_dir, '.config.json')

    status('pl_empty')  # Clear the playlist
    paths = []
    for root, _, files in os.walk(root_dir):
        for f in files:
            path = os.path.join(root, f)
            ext = os.path.splitext(path)
            if ".unwanted" not in path and ext[1].lstrip(".") in VIDEO_FORMATS:
                paths.append(path)

    paths.sort()
    for path in paths:
        print(path)
        status('in_enqueue', input=path)

    playlist_upto_file = None
    seconds = 0
    if os.path.exists(playlist_path):
        with open(playlist_path, 'r') as f:
            save = json.load(f)
            playlist_upto_file = save[KEY_PLAYLIST]
            seconds = save[KEY_TIME]

    for item in run('playlist').iter('leaf'):
        if item.attrib['uri'] == playlist_upto_file or playlist_upto_file is None:
            print("seeking to file", item.attrib['uri'])
            status('pl_play', id=item.attrib['id'])
            break
    seek(seconds)
    threading.Thread(target=time_tracker, args=(playlist_path,)).start()
    threading.Thread(target=track_tracker, args=(config_path,)).start()
    threading.Thread(target=config_checker, args=(config_path,)).start()
    threading.Thread(target=command_recogniser).start()

    while True:
        time.sleep(1000)

def command_recogniser():
    while True:
        run_command(get_rewritten_line())

def run_command(line):
    if line is None:
        return
    print(f"Recieved command '{line}'")
    if line == 'next':
        return status('pl_next')
    if line == 'previous':
        return status('pl_previous')
    if line == 'pause' or line == 'play':
        return status('pl_pause')
    if line == 'subtitle':
        return status('key', val='subtitle-track')
    if line == 'audio':
        return status('key', val='audio-track')
    last_undo_time = global_vars.get(GLOBAL_LAST_UNDO)
    cur_time = global_vars[GLOBAL_LAST_UNDO] = int(status().find(KEY_TIME).text)
    if line == 'chapter':
        return status('key', val='chapter-next')
    if line == 'undo' and last_undo_time is not None:
        return seek(last_undo_time)
    seek_match = re.match(r'seek (-?[0-9]+)', line)
    if seek_match is not None:
        return seek(cur_time + int(seek_match.group(1)))
    if line is not None:
        print(f"Unrecognised command '{line}'")


def config_checker(config_path):
    while True:
        command = input()
        try:
            cmd, *args = command.split(' ', 1)
            if cmd in VALID_MANUAL_KEYS:
                get_updated_config(config_path, **{cmd: args[0]})
                if cmd in (KEY_AUDIO or KEY_SUBS):
                    input(
                        "Please manually set to 1st audio track and disable subtitles")
                # Update the current track
                set_tracks(config_path, status())
            else:
                print("Unknown command")
        except:
            traceback.print_exc()


def get_updated_config(config_path, **updates):
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    if updates:
        config.update(updates)
        with open(config_path, 'w') as f:
            json.dump(config, f)
    return config


def track_tracker(config_path):
    last_file = None
    while True:
        tree = status()
        fname = tree.find(".//info[@name='filename']").text
        if fname != last_file:
            global_vars[GLOBAL_LAST_UNDO] = None
            set_tracks(config_path, tree)

        last_file = fname
        time.sleep(2)


def set_tracks(config_path, tree):
    categories = sorted(tree.findall(".//category/info[@name='Type']/.."), key=lambda x: x.attrib['name'])
    audio_tracks = [x.find("info[@name='Language']").text.lower() for x in
                    categories if x.find("info[@name='Type']").text == "Audio"]
    subtitles = [x.find("info[@name='Language']").text.lower() for x in
                 categories if x.find("info[@name='Type']").text == "Subtitle"]
    eng_audio = [i for i, lang in enumerate(audio_tracks) if "eng" in lang]
    if eng_audio:
        audio = eng_audio[0]
        signs_subs = [i for i, lang in enumerate(subtitles) if "sign" in lang]
        sub = signs_subs[0] + 1 if signs_subs else 0
    else:
        # There could be no english track, or there could be only an english track
        # Assume the former, since if there's only an english track there probably isn't subs anyway.
        audio = 0
        eng_subs = [i for i, lang in enumerate(subtitles) if "eng" in lang]
        sub = eng_subs[0] + 1 if eng_subs else 0
    config = get_updated_config(config_path)
    if KEY_AUDIO in config:
        audio = int(config[KEY_AUDIO])
    if KEY_SUBS in config:
        sub = int(config[KEY_SUBS])
    print(f"Setting audio track to {audio} ({audio_tracks[audio]})")
    track('audio-track', audio)
    print(
        f"Setting subtitle track to {sub} ({subtitles[sub + 1] if sub > 0 else None})")
    track('subtitle-track', sub)


def time_tracker(playlist_path):
    save = {}
    while True:
        # Save where you're up to
        save[KEY_TIME] = int(status().find(KEY_TIME).text)
        if KEY_PLAYLIST in save:
            del save[KEY_PLAYLIST]
        for i, item in enumerate(run('playlist').iter('leaf')):
            if 'current' in item.attrib:
                save[KEY_PLAYLIST] = item.attrib['uri']
        if KEY_PLAYLIST not in save:
            print("Nothing currently playing")
        else:
            with open(playlist_path, 'w') as f:
                json.dump(save, f)
    time.sleep(5)

try:
    main()
except Exception:
    error("".join(traceback.format_exception(*sys.exc_info())))
