import os
import re
import time
from collections import OrderedDict
from datetime import datetime

from pony.orm import Required, PrimaryKey, Optional, ObjectNotFound

import database
from episode import Episode
from interface import status, playlist, maybe_start_process
from torrent import get_directories

VIDEO_FORMATS = ["mkv", "mp4", "avi"]

def get_episodes(directory):
    if isinstance(directory, list):
        episodes = [d for single_dir in directory for d in get_episodes(single_dir).values()]
        episodes.sort(key=lambda x: (x.inferred_episode, x.fname))
        episodes_map = OrderedDict()
        for i, ep in enumerate(episodes):
            expected = episodes[0].inferred_episode + i
            assert ep.inferred_episode == expected, "Expected %d, got %d for %s" % (expected, ep.inferred_episode, ep.fname)
            episodes_map[ep.inferred_episode] = ep
        return episodes_map
    # Single file
    if os.path.isfile(directory):
        return OrderedDict({1: Episode.get_or_create(directory)})
    assert os.path.isdir(directory)
    episodes = []
    for root, _, files in os.walk(directory):
        for f in files:
            path = os.path.join(root, f)
            ext = os.path.splitext(path)
            if ".unwanted" not in path and ext[1].lstrip(
                    ".") in VIDEO_FORMATS:
                episodes.append(Episode.get_or_create(path))
    episodes_map = OrderedDict()
    for i, ep in enumerate(sorted(episodes, key=lambda episode: episode.fname)):
        episodes_map[i + 1] = ep
    return episodes_map


class Series(database.db.Entity, database.Table):
    directory_or_tag = PrimaryKey(str)
    upto = Optional(int)
    last_watched = Required(datetime)

    override_subs = Optional(int)
    override_audio = Optional(int)
    intro_duration = Optional(int)
    is_tag = Required(bool)

    @classmethod
    def get_or_create(cls, tag, directories):
        is_tag = isinstance(directories, list)
        key = tag if is_tag else directories
        try:
            result = cls[key]
            result.last_watched = datetime.now()
            return result
        except ObjectNotFound:
            episodes = get_episodes(directories)
            if episodes:
                return cls(directory_or_tag=key, last_watched=datetime.fromordinal(1), is_tag=is_tag)
            else:
                return None

    @property
    def current_episode(self):
        if self.upto is None:
            return self.episodes[next(iter(self.episodes))]
        return self.episodes[self.upto]

    @property
    def n_episodes(self):
        return next(reversed(self.episodes))

    @property
    def completed(self):
        if self.upto is None:
            return self.current_episode.inferred_episode - 1 if self.is_tag else 0

        return self.upto - (0 if self.current_episode.upto > 5 * 60 else 1)

    @property
    def episodes(self):
        if not hasattr(self, "_episodes"):
            self._episodes = get_episodes(get_directories(self.directory_or_tag) if self.is_tag else self.directory_or_tag)
            for ep in self._episodes.values():
                ep.series = self
        return self._episodes

    @property
    def name(self):
        return self.directory_or_tag if self.is_tag else os.path.basename(self.directory_or_tag)

    def start(self):
        self.last_watched = datetime.now()
        maybe_start_process("C:\Program Files (x86)\VMR Connect\VMRHub.exe")
        time.sleep(1)
        maybe_start_process(r"C:\Program Files\VideoLAN\VLC\vlc.exe")

        # Load the playlist
        status('pl_empty')  # Clear the playlist
        for i, ep in self.episodes.items():
            print(i, ep.fname)
            status('in_enqueue', input=ep.fname)

        print("seeking to file", self.current_episode.fname)
        files = playlist()[0]
        episode = files.get(self.current_episode.fname, files[min(files)])
        status('pl_play', id=episode)

        # Load the correct timestamp
        print("seeking to time", self.current_episode.upto)
        self.current_episode.seek_absolute(self.current_episode.upto)
        time.sleep(2)  # Ensure that status() has time to populate with the correct data
        self.current_episode.on_play(status())

    def update(self):
        st = status()
        ep = playlist()[1]
        assert ep is not None
        current_episode = Episode[ep]
        if self.upto is None or current_episode != self.current_episode:
            for k, v in self.episodes.items():
                if v == current_episode:
                    self.upto = k
                    print(f"Switched episode to Ep{self.upto} ({self.current_episode.fname})")
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
        seek_match = re.match(r'(forwards?|back) ([0-9]+)', line)
        if seek_match is not None:
            return ep.seek_delta(int(seek_match.group(2)) * (1 if seek_match.group(1).startswith("f") else -1))
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

        def test_intro():
            ep.seek_absolute(ep.intro_start - 3)
            time.sleep(3)
            ep.seek_absolute(ep.intro_start + self.intro_duration)
        if line == "start intro":
            ep.intro_start = ep.current_time()
            ep.seek_delta(60)
            return
        if line == "end intro" and ep.intro_start is not None:
            self.intro_duration = ep.current_time() - ep.intro_start
            return test_intro()
        intro_mod_match = re.match('modify (start|end) (-?[0-9]+)', line)
        if intro_mod_match is not None and ep.intro_start is not None and self.intro_duration is not None:
            duration = int(intro_mod_match.group(2))
            if intro_mod_match.group(1) == "start":
                ep.intro_start += duration
                self.intro_duration -= duration
            else:
                self.intro_duration += duration
            return test_intro()
        if line == "intro":
            return ep.seek_delta(self.intro_duration)
        if line is not None:
            print(f"Unrecognised command '{line}'")

    def command_loop(self, getter):
        while True:
            self.run_command(getter())