import os
import sys
import threading
import time
import traceback
from datetime import datetime

from pony.orm import db_session, select, desc

from database import db
from series import Series
from speech import get_rewritten_line
from torrent import select_torrent

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
        [s.delete() for s in Series.select() if not os.path.exists(s.directory)]
        all_series = list(select(s for s in Series).order_by(lambda: desc(s.last_watched)))
        series = all_series[0]
        series.last_watched = datetime.now()
    elif sys.argv[1] == "--":
        series = Series.get_or_create(input("Enter the absolute path to the directory: "))
    elif sys.argv[1] == "--torrent":
        series = Series.get_or_create(select_torrent())
    else:
        series = Series.get_or_create(sys.argv[1])

    if not os.path.exists(series.directory):
        error("Directory doesn't exist:", root_dir)
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
