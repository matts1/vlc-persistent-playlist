import os
import shutil
import time
from collections import OrderedDict

from qbittorrent import Client

def get_client():
    try:
        return Client('http://localhost:8081')
    except BaseException:
        os.startfile("C:\Program Files\qBittorrent\qbittorrent.exe")
        time.sleep(2)
        return Client('http://localhost:8081')

ROOT_DIR = "H:\\unwatched"

CLIENT = get_client()
TORRENTS = CLIENT.torrents()

def get_torrent_dirs():
    paths = OrderedDict()
    torrents = sorted(TORRENTS, key=lambda x: x["added_on"])
    # Only categories with actual things in them.
    categories = {torrent['category'] for torrent in torrents if torrent['category']}
    for torrent in torrents:
        path = torrent['content_path']
        if torrent["progress"] > 0:
            tag = torrent['category']
            if tag == 'Shana Project':
                for category in categories:
                    if category.lower().split(" - ")[0] in torrent['name'].lower().replace("_", " "):
                        print("Filing under", category, ":", torrent['name'])
                        CLIENT.set_category(torrent['hash'], category)
                        tag = category

            if tag:
                paths[tag] = paths.pop(tag, []) + [path]
            else:
                paths[torrent['name']] = path
    return paths

def get_directories(tag):
    return [torrent['content_path'] for torrent in TORRENTS if torrent['category'] == tag]

if __name__ == "__main__":
    get_torrent_dirs()
