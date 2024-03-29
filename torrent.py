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

def category_match(torrent, category):
    return category.lower().split(" - ")[0] in torrent['name'].lower().replace("_", " ").replace(".", " ")


def get_torrents():
    torrents = OrderedDict()
    initial_torrents = sorted(TORRENTS, key=lambda x: x["added_on"])
    # Only categories with actual things in them.
    categories = {torrent['category'] for torrent in initial_torrents if torrent['category']}
    for torrent in initial_torrents:
        path = torrent['content_path']
        tag = torrent['category']
        if tag == 'Shana Project' or not tag and "no_category" not in torrent["tags"]:
            for category in categories:
                if category_match(torrent, category):
                    print("Filing under", category, ":", torrent['name'])
                    CLIENT.set_category(torrent['hash'], category)
                    torrent['category'] = tag = category
        if tag == 'Shana Project':
            while True:
                torrent['category'] = tag = category = input(f"Enter a category for {torrent['name']}\n")
                if category_match(torrent, category):
                    CLIENT.create_category(category)
                    categories.add(category)
                    CLIENT.set_category(torrent['hash'], category)
                    break

        if torrent["progress"] > 0:
            if tag:
                torrents[tag] = torrents.pop(tag, []) + [torrent]
            else:
                torrents[torrent['name']] = torrent
    assert 'Shana Project' not in torrents, "Shana project not empty"
    return torrents

if __name__ == "__main__":
    get_torrents()
