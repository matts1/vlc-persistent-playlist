import os
import re
import time
from collections import OrderedDict
from datetime import datetime

from pony.orm import Required, PrimaryKey, Optional, ObjectNotFound

import database
from episode import Episode
from interface import status, playlist, maybe_start_process

VIDEO_FORMATS = ["mkv", "mp4", "avi"]
END_OF_EPISODE_PERCENTAGE = 0.8


def get_episodes(torrent, fill_ep_num=True):
    if isinstance(torrent, list):
        episodes = []
        for t in torrent:
            episodes.append(next(iter(get_episodes(t, fill_ep_num=False).values())))
            tag = t['tags']
            if tag:
                assert tag.startswith("#")
                episodes[-1]._ep_num = float(tag[1:])
        episodes.sort(key=lambda x: (x.inferred_episode, x.fname))
        episodes_map = OrderedDict()
        expected = [episodes[0].inferred_episode]
        for i, ep in enumerate(episodes):
            assert ep.inferred_episode in expected, "Expected %s, got %d for %s" % (
            expected, ep.inferred_episode, ep.fname)
            expected = [ep.inferred_episode + 0.5, ep.inferred_episode + 1]
            episodes_map[ep.inferred_episode] = ep
            # Account for ep17.5, etc. Assume it's 18.
        return episodes_map

    directory = torrent['content_path']
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
    for i, ep in enumerate(sorted(episodes, key=lambda episode: (os.path.dirname(episode.fname), episode.stripped_fnames[-1]))):
        episodes_map[i + 1] = ep
        if fill_ep_num:
            ep._ep_num = i + 1
    return episodes_map


class Series(database.db.Entity, database.Table):
    directory_or_tag = PrimaryKey(str)
    upto = Optional(float)
    last_watched = Required(datetime)

    override_subs = Optional(int)
    override_audio = Optional(int)
    intro_duration = Optional(int)
    autoskip_duration = Optional(int)
    autoskip_chapters = Optional(int)
    autonext_time = Optional(int)
    is_tag = Required(bool)

    @property
    def episodes_by_index(self):
        return list(self.episodes.values())

    @classmethod
    def get_or_create(cls, tag, torrents):
        is_tag = isinstance(torrents, list)
        key = tag if is_tag else torrents['content_path']
        added_on = max(t['added_on'] for t in torrents) if is_tag else torrents['added_on']
        try:
            result = cls[key]
            result.torrents = torrents
            if result.last_watched is None:
                result.last_watched = datetime.fromtimestamp(0)
        except ObjectNotFound:
            if get_episodes(torrents):
                result = cls(directory_or_tag=key, last_watched=datetime.fromordinal(1), is_tag=is_tag)
                result.torrents = torrents
            else:
                return None
        result.added_on = datetime.fromtimestamp(added_on)
        return result

    def __lt__(self, other):
        key = lambda x: (max(x.last_watched, x.added_on), x.added_on)
        return key(self) < key(other)

    @property
    def current_episode(self) -> Episode:
        if self.upto is None or self.upto not in self.episodes:
            return self.episodes_by_index[0]
        return self.episodes[self.upto]

    def episode_before(self, ep: Episode) -> float:
        idx = self.episodes_by_index.index(ep)
        if idx == 0:
            return 0
        return self.episodes_by_index[idx - 1].inferred_episode

    @property
    def n_episodes(self):
        return next(reversed(self.episodes))

    @property
    def completed(self):
        if self.upto is None:
            return int(self.current_episode.inferred_episode) - 1 if self.is_tag else 0

        if self.current_episode.upto > 5 * 60:
            return self.current_episode.inferred_episode
        return self.episode_before(self.current_episode)

    @property
    def episodes(self):
        if not hasattr(self, "_episodes"):
            self._episodes = get_episodes(self.torrents)
            for ep in self._episodes.values():
                ep.series = self
        return self._episodes

    @property
    def name(self):
        return self.directory_or_tag if self.is_tag else os.path.basename(self.directory_or_tag)

    def start(self):
        self.last_watched = datetime.now()
        # maybe_start_process("C:\Program Files (x86)\VMR Connect\VMRHub.exe")
        # time.sleep(1)
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
        st = status()
        self.current_episode.on_play(st)
        print(f"Up to {st.find('position').text}/1, {st.find('time').text} seconds")
        percentage_complete = float(st.find('position').text)
        if percentage_complete > END_OF_EPISODE_PERCENTAGE:
            status('pl_next')

    def update(self):
        st = status()
        current_time = int(st.find('time').text)
        episodes, ep = playlist()
        if ep is None:
            ep = sorted(episodes)[-1]
        current_episode = Episode[ep]
        if self.autonext_time is not None and current_time > self.autonext_time:
            status('pl_next')
        if self.upto is None or current_episode != self.current_episode:
            for k, v in self.episodes.items():
                if v == current_episode:
                    if self.autoskip_duration is not None:
                        current_episode.seek_absolute(self.autoskip_duration)
                    for i in range(self.autoskip_chapters or 0):
                        ep.seek_command(status, 'key', val='chapter-next')
                    self.upto = k
                    print(f"Switched episode to Ep{self.upto} ({self.current_episode.fname})")
                    self.current_episode.on_play(st)
        current_episode.upto = current_time

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

        chapter_skip_match = re.match("autoskip chapter( [0-9]+)?", line)
        if chapter_skip_match is not None:
            self.autoskip_chapters = 1 if chapter_skip_match.group(1) == "" else int(chapter_skip_match)
            return

        if line == "autoskip":
            self.autoskip_duration = self.current_episode.current_time()
            return
        if line == "autonext":
            self.autonext_time = self.current_episode.current_time()
            return

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