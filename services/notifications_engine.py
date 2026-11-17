"""
services/notifications_engine.py - Remote Notifications & Updates Engine.
Fetches public notification feed over HTTPS in a non-blocking background thread,
caches notifications locally in UserData/notifications_cache.json, and tracks read/unread states.
"""
import os
import sys
import json
import time
import csv
import io
import threading
import urllib.request
from utils import get_user_data_dir

REMOTE_FEED_URL = "https://docs.google.com/spreadsheets/d/1V1cAJAhc09aWtjTBQ2hK2lc4_QJVVWjZwIUEcqUxNsI/export?format=csv"


class NotificationsEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NotificationsEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.cache_file = os.path.join(get_user_data_dir(), "notifications_cache.json")
        self.lock = threading.Lock()
        
        self.notifications = []
        self.read_ids = set()
        self.dismissed_ids = set()
        self.last_fetched = 0.0
        
        self.load_cache()

    def load_cache(self):
        with self.lock:
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.notifications = data.get("notifications", [])
                        self.read_ids = set(data.get("read_ids", []))
                        self.dismissed_ids = set(data.get("dismissed_ids", []))
                        self.last_fetched = data.get("last_fetched", 0.0)
                except Exception as e:
                    print(f"[NotificationsEngine] Cache load error: {e}")

    def save_cache(self):
        with self.lock:
            try:
                data = {
                    "notifications": self.notifications,
                    "read_ids": list(self.read_ids),
                    "dismissed_ids": list(self.dismissed_ids),
                    "last_fetched": self.last_fetched
                }
                temp_file = self.cache_file + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(temp_file, self.cache_file)
            except Exception as e:
                print(f"[NotificationsEngine] Cache save error: {e}")

    def fetch_remote_notifications(self):
        """Fetches latest notifications from remote endpoint."""
        try:
            req = urllib.request.Request(
                REMOTE_FEED_URL, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Vertex/2.0.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                csv_raw = resp.read().decode('utf-8', errors='ignore')
                reader = csv.DictReader(io.StringIO(csv_raw))
                fetched_items = []
                for row in reader:
                    notif_id = row.get('id', '').strip()
                    if not notif_id:
                        continue
                    item = {
                        'id': notif_id,
                        'date': row.get('date', '').strip(),
                        'type': row.get('type', 'ANNOUNCEMENT').strip().upper(),
                        'title': row.get('title', '').strip(),
                        'message': row.get('message', '').strip(),
                        'action_type': row.get('action_type', 'NONE').strip().upper(),
                        'action_value': row.get('action_value', '').strip(),
                        'priority': row.get('priority', 'NORMAL').strip().upper()
                    }
                    fetched_items.append(item)

                if fetched_items:
                    with self.lock:
                        self.notifications = fetched_items
                        self.last_fetched = time.time()
                    self.save_cache()
                    print(f"[NotificationsEngine] Successfully fetched {len(fetched_items)} notifications.")
                    return True
        except Exception:
            print("[NotificationsEngine] Remote notification feed temporarily unavailable.")
        return False

    def fetch_async(self, callback=None):
        """Runs fetch_remote_notifications in a background daemon thread."""
        def worker():
            success = self.fetch_remote_notifications()
            if callback:
                try:
                    callback(success)
                except Exception:
                    pass
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def get_notifications(self, category_filter="ALL", search_query=""):
        with self.lock:
            items = []
            for notif in self.notifications:
                notif_id = notif.get('id', '')
                if notif_id in self.dismissed_ids:
                    continue

                ntype = notif.get('type', 'ANNOUNCEMENT')
                if category_filter and category_filter != "ALL":
                    if category_filter == "APP_UPDATE" and ntype != "APP_UPDATE":
                        continue
                    elif category_filter == "MODULE" and ntype not in ["MODULE_RELEASE", "MODULE_UPDATE"]:
                        continue
                    elif category_filter == "ANNOUNCEMENT" and ntype != "ANNOUNCEMENT":
                        continue

                if search_query:
                    sq = search_query.lower()
                    title = notif.get('title', '').lower()
                    msg = notif.get('message', '').lower()
                    if sq not in title and sq not in msg:
                        continue

                item_copy = dict(notif)
                item_copy['is_read'] = notif_id in self.read_ids
                items.append(item_copy)
            return items

    def get_unread_count(self):
        with self.lock:
            count = 0
            for notif in self.notifications:
                notif_id = notif.get('id', '')
                if notif_id not in self.dismissed_ids and notif_id not in self.read_ids:
                    count += 1
            return count

    def get_high_priority_unreads(self):
        with self.lock:
            unreads = []
            for notif in self.notifications:
                notif_id = notif.get('id', '')
                if notif_id not in self.dismissed_ids and notif_id not in self.read_ids:
                    if notif.get('priority') == 'HIGH' or notif.get('type') == 'APP_UPDATE':
                        unreads.append(dict(notif))
            return unreads

    def mark_as_read(self, notif_id):
        with self.lock:
            self.read_ids.add(notif_id)
        self.save_cache()

    def mark_all_as_read(self):
        with self.lock:
            for notif in self.notifications:
                notif_id = notif.get('id', '')
                if notif_id:
                    self.read_ids.add(notif_id)
        self.save_cache()

    def dismiss_notification(self, notif_id):
        with self.lock:
            self.dismissed_ids.add(notif_id)
        self.save_cache()


def get_notifications_engine():
    return NotificationsEngine()
