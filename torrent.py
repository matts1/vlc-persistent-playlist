import os
import shutil
import time

from qbittorrent import Client

def get_client():
    try:
        return Client('http://localhost:8081')
    except BaseException:
        os.startfile("C:\Program Files\qBittorrent\qbittorrent.exe")
        time.sleep(2)
        return Client('http://localhost:8081')

ROOT_DIR = "H:\\unwatched"


def get_torrent_dirs():
    paths = []
    for torrent in sorted(get_client().torrents(), key=lambda x: x["added_on"]):
        path = os.path.join(torrent['save_path'], torrent['name'])
        if torrent["progress"] > 0:
            paths.append(path)
    return paths

def select_torrent():
    torrents = list(reversed(get_torrent_dirs()))
    for i, torrent in reversed(list(enumerate(torrents))):
        print(i, os.path.basename(torrent))
    return torrents[int(input("Enter the torrent number: "))]

if __name__ == "__main__":
    torrent_dirs = get_torrent_dirs()
    for root, _, files in os.walk(ROOT_DIR):
        if not any(os.path.commonprefix([root, d]) == d for d in torrent_dirs):
            print(root)
            for f in files:
                if os.path.join(root, f) not in torrent_dirs:
                    print("    " + f)
            if root != ROOT_DIR and (files == [".playlist"] or input("Delete? (y/n)").lower() ==  "y"):
                shutil.rmtree(root)
