import asyncio
import requests
from configparser import ConfigParser
from collections import namedtuple
import psycopg2
from multiprocessing import Pool
from psycopg2 import pool
import tqdm
import aiohttp

NUM_OF_DB_WORKER = 100
NUM_OF_DB_QUEUE = 300
NUM_OF_DB_CONNECTION_POOL = 100
NUM_OF_HTTP_WORKER = 300
NUM_OF_HTTP_QUEUE = 1

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
  def __init__(self, id: int, type: str, time: int=0, text: str="", by: str="", poll: int=0, score: int=0, deleted: bool=False):
    super().__init__(id, type, by, time, [])
    self.text = text
    self.poll = poll
    self.by = by
    self.score = score
    self.deleted = deleted

DatabaseConfig = namedtuple('DatabaseConfig', 'host port database user password')
def config(filename='database.ini') -> DatabaseConfig:
    parser = ConfigParser()
    parser.read(filename)
    if parser.has_section('postgresql'):
        return DatabaseConfig(**parser._sections['postgresql'])
    else:
        raise Exception('Section {0} not found in the {1} file'.format('postgresql', filename))

db_pool = psycopg2.pool.ThreadedConnectionPool(1, NUM_OF_DB_CONNECTION_POOL, **config()._asdict())
def insert_story_to_db(story: Story):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO items (id, "by", "time", title, score, url, text, descendants, dead, deleted, type)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;
        """,
        (story.id, story.by, story.time, story.title, story.score, story.url, story.text, story.descendants, story.dead, story.deleted, story.type))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

def insert_comment_to_db(comment: Comment):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO items (id, "by", "time", text, deleted, parent, dead, type)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;
        """,
        (comment.id, comment.by, comment.time, comment.text, comment.deleted, comment.parent, comment.dead, comment.type))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

def insert_pollopts_to_db(poll_option: PollOption):
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO items (id, "by", "time", text, poll, score, type)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s) ON CONFLICT DO NOTHING;
        """,
        (poll_option.id, poll_option.by, poll_option.time, poll_option.text, poll_option.poll, poll_option.score, poll_option.type))
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

async def db_writer_worker(input_queue: asyncio.Queue):
    while True:
        data = await input_queue.get()
        if isinstance(data, Comment):
            insert_comment_to_db(data)
        elif isinstance(data, Story):
            insert_story_to_db(data)
        elif isinstance(data, PollOption):
            insert_pollopts_to_db(data)
        input_queue.task_done()

def get_last_id() -> int:
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("SELECT max(id) FROM items;", ())
    
    rows = cur.fetchall()
    conn.commit()
    cur.close()
    return int(rows[0][0]) if rows[0][0] else 0

async def get_items(session: aiohttp.ClientSession, id_queue: asyncio.Queue, db_queue: asyncio.Queue):
    while True:
        id = await id_queue.get()
        url = f"https://hacker-news.firebaseio.com/v0/item/{id}.json"

        try:
            async with session.get(url) as raw_response:
                response = await raw_response.json()
                if response['type'] == 'story' or response['type'] == 'poll' or response['type'] == 'job':
                    o = Story(**response)
                    await db_queue.put(o)
                elif response['type'] == 'comment':
                    o = Comment(**response)
                    await db_queue.put(o)
                elif response['type'] == 'pollopt':
                    o = PollOption(**response)
                    await db_queue.put(o)
                else:
                    print(f"Unknown type {response['type']} for id {id}")
            id_queue.task_done()
        except Exception as e:
            id_queue.task_done()
            await id_queue.put(id)
            print(f"Error: {e}, response: {response}")

def get_max_id() -> int:
    r = requests.get("https://hacker-news.firebaseio.com/v0/maxitem.json")
    return int(r.text)

def get_id() -> int:
    n = get_last_id()
    while n < get_max_id():
        yield n
        n += 1

async def main():
    db_queue = asyncio.Queue(maxsize=NUM_OF_DB_QUEUE)
    id_queue = asyncio.Queue(maxsize=NUM_OF_HTTP_QUEUE)

    pbar = tqdm.tqdm(range(get_last_id() + 1, get_max_id() + 1), initial=(get_last_id() + 1), total=(get_max_id() + 1))
    async with aiohttp.ClientSession() as session:

        for _ in range(NUM_OF_DB_WORKER):
            asyncio.create_task(db_writer_worker(db_queue))
        for _ in range(NUM_OF_HTTP_WORKER):
            asyncio.create_task(get_items(session, id_queue, db_queue))
        for id in pbar:
            await id_queue.put(id)

        await id_queue.join()
        await db_queue.join()


if __name__ == '__main__':
    asyncio.run(main())
    db_pool.closeall
