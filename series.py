import os
import re
import time
from datetime import datetime

from pony.orm import Required, PrimaryKey, Optional, ObjectNotFound

import database
from episode import Episode
from interface import status, playlist, maybe_start_process

VIDEO_FORMATS = ["mkv", "mp4"]

def episodes(directory):
    # Single file
    if os.path.isfile(directory):
        return [Episode.get_or_create(directory)]
    else:
        episodes = []
        for root, _, files in os.walk(directory):
            for f in files:
                path = os.path.join(root, f)
                ext = os.path.splitext(path)
                if ".unwanted" not in path and ext[1].lstrip(
                        ".") in VIDEO_FORMATS:
                    episodes.append(Episode.get_or_create(path))
        return episodes


class Series(database.db.Entity, database.Table):
    directory = PrimaryKey(str)
    current_episode = Required(Episode)
    last_watched = Required(datetime)

    override_subs = Optional(int)
    override_audio = Optional(int)

    @classmethod
    def get_or_create(cls, directory):
        try:
            result = cls[directory]
            result.last_watched = datetime.now()
            return result
        except ObjectNotFound:
            return cls(directory=directory, current_episode=episodes(directory)[0], last_watched=datetime.now())

    def start(self):
        maybe_start_process("C:\Program Files (x86)\VMR Connect\VMRHub.exe")
        time.sleep(1)
        maybe_start_process(r"C:\Program Files\VideoLAN\VLC\vlc.exe")

        # Load the playlist
        status('pl_empty')  # Clear the playlist
        for ep in sorted(episodes(self.directory), key=lambda ep: ep.fname):
            print(ep.fname)
            status('in_enqueue', input=ep.fname)

        print("seeking to file", self.current_episode.fname)
        status('pl_play', id=playlist()[0][self.current_episode.fname])

        # Load the correct timestamp
        print("seeking to time", self.current_episode.upto)
        self.current_episode.seek_absolute(self.current_episode.upto)
        time.sleep(2)  # Ensure that status() has time to populate with the correct data
        self.current_episode.on_play(status())

    def update(self):
        st = status()
        current_episode = Episode[playlist()[1]]
        if current_episode != self.current_episode:
            print(f"Switched episode to {current_episode.fname}")
            self.current_episode = current_episode
            self.current_episode.on_play(st)
        current_episode.upto = int(st.find('time').text)

    def run_command(self, line):
        if line is None:
            return
        print(f"Recieved command '{line}'")
        if line == 'next':
            return status('pl_next')
        if line == 'previous':
            return status('pl_previous')
        if line == 'pause' or line == 'play':
            return status('pl_pause')
        ep = self.current_episode
        if line == 'subtitle':
            return ep.sub_tracks.increment()
        if line == 'audio':
            return ep.audio_tracks.increment()
        if line == 'chapter':
            return ep.seek_command(status, 'key', val='chapter-next')
        if line == 'undo' and ep.last_undo_time is not None:
            return ep.seek_absolute(ep.last_undo_time)
        seek_match = re.match(r'seek (-?[0-9]+)', line)
        if seek_match is not None:
            return ep.seek_delta(int(seek_match.group(1)))
        override_match = re.match(r'override (audio|subtitles?) ([0-9]+)', line)
        if override_match is not None:
            override_num = int(override_match.group(2))
            if override_match.group(1) == "audio":
                if not ep.audio_tracks.valid_track(override_num):
                    print("Invalid track selection")
                    return
                self.override_audio = override_num
            else:
                if not ep.sub_tracks.valid_track(override_num):
                    print("Invalid track selection")
                    return
                self.override_subs = override_num
            ep.on_play(status())  # This should trigger changing them
            return
        if line == "delete audio override":
            self.override_audio = None
            return ep.on_play(status())

        if line == "delete subtitles override" or line == "delete subtitle override":
            self.override_subs = None
            return ep.on_play(status())
        if line is not None:
            print(f"Unrecognised command '{line}'")

    def command_loop(self, getter):
        while True:
            self.run_command(getter())