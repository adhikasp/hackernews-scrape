import asyncio
import json
import threading
import requests
from configparser import ConfigParser
from collections import namedtuple
import psycopg2
from multiprocessing import Pool
from psycopg2 import pool
import tqdm
import aiohttp
import queue
import time

class Item(object):
    def __init__(self, id: int, type: str, by: str, time: int, kids: list[int]):
        self.id = id
        self.type = type
        self.by = by
        self.time = time
        self.kids = kids

class Comment(Item):
  def __init__(self, id: int, type: str, parent: str, time: int=0, kids: list[int]=[], text: str="", deleted: bool=False, by: str="", dead: bool=False):
    super().__init__(id, type, by, time, kids)
    self.text = text
    self.deleted = deleted
    self.parent = parent
    self.dead = dead
    self.by = by
    self.kids = kids

class Story(Item):
  def __init__(self, id: int, type: str, time: int=0, by: str="", title: str="", descendants: int=0, score: int=0, url: str="", kids: list[int]=[], dead: bool=False, text: str="", deleted: bool=False, parts: list[int]=[]):
    super().__init__(id, type, by, time, kids)
    self.title = title
    self.type = type
    self.descendants = descendants
    self.score = score
    self.url = url
    self.dead = dead
    self.deleted = deleted
    self.text = text
    self.by = by

class PollOption(Item):
  def __init__(self, id: int, type: str, time: int=0, text: str="", by: str="", poll: int=0, score: int=0):
    super().__init__(id, type, by, time, [])
    self.text = text
    self.poll = poll
    self.by = by
    self.score = score

DatabaseConfig = namedtuple('DatabaseConfig', 'host port database user password')
def config(filename='database.ini') -> DatabaseConfig:
    parser = ConfigParser()
    parser.read(filename)
    if parser.has_section('postgresql'):
        return DatabaseConfig(**parser._sections['postgresql'])
    else:
        raise Exception('Section {0} not found in the {1} file'.format('postgresql', filename))

db_pool = psycopg2.pool.ThreadedConnectionPool(20, 20, **config()._asdict())
def insert_story_to_db(story: Story):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO stories (id, "by", "time", title, score, url, text, descendants, dead, deleted, type)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (story.id, story.by, story.time, story.title, story.score, story.url, story.text, story.descendants, story.dead, story.deleted, story.type))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

def insert_comment_to_db(comment: Comment):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO comments (id, "by", "time", text, deleted, parent, dead)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s);
        """,
        (comment.id, comment.by, comment.time, comment.text, comment.deleted, comment.parent, comment.dead))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

def insert_pollopts_to_db(poll_option: PollOption):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pollopts (id, "by", "time", text, poll, score)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s);
        """,
        (poll_option.id, poll_option.by, poll_option.time, poll_option.text, poll_option.poll, poll_option.score))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

def db_writer_worker(input_queue: queue.Queue):
    while True:
        data = input_queue.get()
        if data is None:
            break
        if isinstance(data, Comment):
            insert_comment_to_db(data)
        elif isinstance(data, Story):
            insert_story_to_db(data)
        elif isinstance(data, PollOption):
            insert_pollopts_to_db(data)

def get_last_id() -> int:
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("SELECT max(max) FROM (SELECT max(stories.id) from stories UNION SELECT max(comments.id) FROM comments) as subquery;", ())
    
    rows = cur.fetchall()
    conn.commit()
    cur.close()
    return int(rows[0][0]) if rows[0][0] else 0

async def get_items(session: aiohttp.ClientSession, id: int, db_queue: queue.Queue, sem: asyncio.Semaphore):
    url = f"https://hacker-news.firebaseio.com/v0/item/{id}.json"

    try:
        async with session.get(url) as raw_response:
            response = await raw_response.json()
            if response['type'] == 'story' or response['type'] == 'poll' or response['type'] == 'job':
                o = Story(**response)
                db_queue.put(o)
            elif response['type'] == 'comment':
                o = Comment(**response)
                db_queue.put(o)
            elif response['type'] == 'pollopt':
                o = PollOption(**response)
                db_queue.put(o)
            else:
                print(f"Unknown type {response['type']} for id {id}")
    except Exception as e:
        print(f"Error: {e}, response: {response}")
    finally:
        sem.release()

def get_max_id() -> int:
    r = requests.get("https://hacker-news.firebaseio.com/v0/maxitem.json")
    return int(r.text)

def get_id() -> int:
    n = get_last_id()
    while n < get_max_id():
        yield n
        n += 1

async def main(db_queue: queue.Queue):
    pbar = tqdm.tqdm(range(get_last_id() + 1, get_max_id() + 1), initial=(get_last_id() + 1), total=(get_max_id() + 1))
    N = 100
    sem = asyncio.Semaphore(N)
    async with aiohttp.ClientSession() as session:
        for id in pbar:
            await sem.acquire()
            asyncio.create_task(get_items(session, id, db_queue, sem))
        for _ in range(N):
            await sem.acquire()

def is_any_thread_alive(threads):
    return True in [t.is_alive() for t in threads]

if __name__ == '__main__':
    db_queue = queue.Queue()
    db_thread = threading.Thread(target=db_writer_worker, args=(db_queue,), daemon=True)
    db_thread.start()

    asyncio.run(main(db_queue))

    while is_any_thread_alive([db_thread]):
        time.sleep(0)

    db_queue.put(None)
    db_thread.join()
    db_pool.closeall
