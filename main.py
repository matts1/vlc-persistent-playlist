import os
import sys
import threading
import time
import traceback

from pony.orm import db_session, select, desc

from database import db
from series import Series
from speech import get_rewritten_line
from torrent import get_torrents

db.generate_mapping(create_tables=True)


def error(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)
    time.sleep(10)
    exit(1)


def loop_and_sleep(duration, fn, *args, **kwargs):
    def new_fn():
        while True:
            fn(*args, **kwargs)
            time.sleep(duration)
    threading.Thread(target=new_fn).start()


@db_session
def main():
    if len(sys.argv) < 2:
        [s.delete() for s in Series.select() if not s.is_tag and not os.path.exists(s.directory_or_tag)]
        all_series = sorted(Series.select(), key=lambda s: s.last_watched, reverse=True)
        series = all_series[0]
    elif sys.argv[1] == "--torrent":
        all_series = [Series.get_or_create(name, torrents) for name, torrents in reversed(get_torrents().items())]
        all_series = [s for s in all_series if s is not None and (s.completed == 0 or s.completed != s.n_episodes)]

        for i, s in reversed(list(enumerate(all_series))):
            if s.completed > 0:
                progress = f'({s.completed: >2}/{s.n_episodes: <2})'
            else:
                progress = ' ' * 7
            print(f'{i: <3} {progress} {s.name}')

        series = all_series[int(sys.argv[2] if len(sys.argv) > 2 else input("Enter the torrent number: "))]

    series.start()
    threading.Thread(target=series.command_loop, args=(input,)).start()
    threading.Thread(target=series.command_loop, args=(get_rewritten_line,)).start()
    while True:
        series.update()
        db.commit()
        time.sleep(2)


try:
    main()
except Exception:
    error("".join(traceback.format_exception(*sys.exc_info())))
