import datetime
import os
import shutil

from pony.orm import Database

DB_FILE = 'H:/unwatched/db.sqlite3'

BACKUP_DB_DIRECTORY = 'H:/unwatched/db_backup'

db = Database()
db.bind('sqlite', DB_FILE, create_db=True)

shutil.copyfile(DB_FILE, os.path.join(BACKUP_DB_DIRECTORY, f"{datetime.date.today().strftime('%Y-%m-%d')}.sqlite3"))


class Table(object):
    @classmethod
    def create_or_update(cls, **kwargs):
        old_obj = cls.get(**dict((k, kwargs[k]) for k in cls._pk_columns_))
        if old_obj is None:
            return cls(**kwargs)
        for k, v in kwargs.items():
            if k not in cls._pk_columns_:
                setattr(old_obj, k, v)
        return old_obj

    @classmethod
    def delete_or_err(cls, err=None, **kwargs):
        cls.get_or_err(err, **kwargs).delete()
