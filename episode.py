import os
import re

from pony.orm import PrimaryKey, Required, ObjectNotFound

import database
from interface import status

R = lambda x: lambda s: re.sub(x, "", s, flags=re.I)

TRANSFORMATIONS = [
    os.path.basename,
    str.lower,
    R(r"\[[^]]+\]"),
    R(r"((1440|1080|720|540)p)"),
    R(r"1920|1080"),
    R(r"[57]\.1"),
    R(r"[Hx]\.?26[45]"),
    R(r"S[0-9]+E?"),
    R(r"\[[A-Z0-9]+\]"),
    R(r"v[0-9]+(\.[0-9]+)?"),
    R(r"20[012][0-9]"),
    R(r"S?[0-9]+x"),
    R(r"Chapter [0-9]+"),
    R(r"1st|2nd|3rd|[4-9]th"),
    R(r"part [0-9]+"),
    R(r"^\s+[0-9]+")
    # lambda f: f.replace(".", " ")
]


def while_playing(fn):
    def new_fn(*args, **kwargs):
        assert args[0].series is not None
        return fn(*args, **kwargs)
    return new_fn


class TrackSet(object):
    def __init__(self, st):
        streams = sorted(
                [x for x in st.findall(".//category/info[@name='Type']/..") if x.find("info[@name='Type']").text == self.name.title()], key=lambda x: int(x.attrib['name'].replace("Stream ", "")))
        def track_name(x):
            tag = x.find("info[@name='Description']")
            if tag is None:
                tag = x.find("info[@name='Language']")
            return "???" if tag is None else tag.text.lower()
        self.tracks = [None] + list(map(track_name, streams))

    def get_index(self, matcher):
        tracks = [i for i, lang in enumerate(self.tracks[1:]) if matcher(lang)]
        return tracks[0] + 1 if tracks else 0

    def set_track(self, index):
        assert self.valid_track(index)
        print(f"Setting {self.name} track to {index} ({self.tracks[index]})")
        while self.current != index:
            self.increment()

    def increment(self):
        self.current = max((self.current + 1) % len(self.tracks), self.low)
        status("key", val=f"{self.name}-track")

    def valid_track(self, index):
        return index >= self.low and index < len(self.tracks)


class SubTrackSet(TrackSet):
    name = "subtitle"
    current = 0
    low = 0


class AudioTrackSet(TrackSet):
    name = "audio"
    current = 1
    low = 1


class Episode(database.db.Entity, database.Table):
    fname = PrimaryKey(str)
    upto = Required(int, default=0)
    last_undo_time = None
    intro_start = None
    _ep_num = None

    @classmethod
    def get_or_create(cls, item, *args, tag=None, **kwargs):
        try:
            res = cls[item]
        except ObjectNotFound:
            res = cls(fname=item)
        return res

    @while_playing
    def seek_delta(self, delta):
        self.last_undo_time = int(status().find('time').text)
        status('seek', val=self.last_undo_time + delta)

    @while_playing
    def seek_absolute(self, timestamp):
        self.seek_command(status, 'seek', val=timestamp)

    @while_playing
    def seek_command(self, fn, *args, **kwargs):
        self.last_undo_time = self.current_time()
        fn(*args, **kwargs)

    @while_playing
    def current_time(self):
        return int(status().find('time').text)

    @while_playing
    def on_play(self, st):
        # It caches the current track, so we can't recreate this.
        if not hasattr(self, 'audio_tracks'):
            self.audio_tracks = AudioTrackSet(st)
            self.sub_tracks = SubTrackSet(st)
        eng_audio = self.audio_tracks.get_index(lambda lang: "eng" in lang)
        override_audio = self.series.override_audio
        override_subs = self.series.override_subs
        if override_subs is not None:
            self.sub_tracks.set_track(override_subs)
        elif override_audio is not None or eng_audio:
            # If you override the audio, obviously it's to make it english, so assume we found english audio.
            if override_audio:
                self.audio_tracks.set_track(override_audio)
            self.sub_tracks.set_track(self.sub_tracks.get_index(lambda lang: "sign" in lang))
        else:
            # There could be no english track, or there could be only an english track. Assume the latter.
            eng_track = self.sub_tracks.get_index(
                lambda lang: "sign" not in lang and "eng" in lang)
            if not eng_track:
                eng_track = 1 if len(self.sub_tracks.tracks) > 1 else 0
            self.sub_tracks.set_track(eng_track)

    @property
    def stripped_fnames(self):
        stages = [self.fname]
        for t in TRANSFORMATIONS:
            stages.append(t(stages[-1]))
        return stages

    @property
    def inferred_episode(self) -> float:
        if self._ep_num is not None:
            return self._ep_num
        stages = self.stripped_fnames
        result = re.findall(r"\b([0-9]+)(\.5)?\b", stages[-1])
        stages_fmt = '\n'.join(stages)
        assert result, f"No numbers in:\n{stages_fmt}"
        if len(result) > 1:
            print(f"WARNING: Got multiple numbers in:\n{stages_fmt}\nGot: {result}. Assuming {result[-1]}")
        return int(result[-1][0]) + (0.5 if result[-1][1] else 0)
