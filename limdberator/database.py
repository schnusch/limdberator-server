"""
limdberator
Copyright (C) 2022  schnusch

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import asyncio
import sqlite3
from types import TracebackType
from typing import Iterator, List, Mapping, Optional, Sequence, Tuple, Type, Union

from .types import ScrapedPerson, ScrapedTitle


class SharedConnection:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.lock = asyncio.Lock()
        self.cursor = None  # type: Optional[sqlite3.Cursor]
        self.conn.isolation_level = None

    async def __aenter__(self) -> sqlite3.Cursor:
        """Lock the connection, return a cursor, and create a transaction."""

        await self.lock.acquire()
        try:
            self.cursor = self.conn.cursor()
            self.cursor.execute("BEGIN")
            return self.cursor
        except Exception:
            self.cursor = None
            self.lock.release()
            raise

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        try:
            assert self.cursor is not None
            try:
                if exc_type is not None:
                    raise Exception
                self.cursor.execute("COMMIT")
            except Exception:
                self.cursor.execute("ROLLBACK")
        finally:
            self.cursor = None
            self.lock.release()


def init_database(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS scrapes ("
        "id INTEGER PRIMARY KEY, "
        "timestamp INTEGER NOT NULL"
        ")"
    )
    cursor.execute("CREATE TABLE IF NOT EXISTS _changes (id INTEGER PRIMARY KEY)")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS changes ("
        "id INTEGER NOT NULL REFERENCES _changes(id), "
        "scrape_id INTEGER NOT NULL REFERENCES scrapes(id)"
        ")"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS title_info ("
        "change_id INTEGER PRIMARY KEY REFERENCES _changes(id), "
        "title_id TEXT NOT NULL, "
        "key TEXT NOT NULL, "
        "value BLOB NOT NULL, "
        "UNIQUE(title_id, key, value)"
        ")"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS title_tags ("
        "change_id INTEGER PRIMARY KEY REFERENCES _changes(id), "
        "title_id TEXT NOT NULL, "
        "tag TEXT, "
        "UNIQUE(title_id, tag)"
        ")"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS people_info ("
        "change_id INTEGER PRIMARY KEY REFERENCES _changes(id), "
        "person_id TEXT NOT NULL, "
        "key TEXT NOT NULL, "
        "value BLOB NOT NULL, "
        "UNIQUE(person_id, key, value)"
        ")"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS credits ("
        "change_id INTEGER PRIMARY KEY REFERENCES _changes(id), "
        "title_id TEXT NOT NULL, "
        "credit_type TEXT, "
        "person_id TEXT NOT NULL, "
        "UNIQUE(title_id, credit_type, person_id)"
        ")"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS credit_tags ("
        "change_id INTEGER PRIMARY KEY REFERENCES _changes(id), "
        "title_id TEXT NOT NULL, "
        "person_id TEXT NOT NULL, "
        "tag TEXT, "
        "UNIQUE(title_id, person_id, tag)"
        ")"
    )


def insert_new_scrape(cursor: sqlite3.Cursor, timestamp: int) -> int:
    cursor.execute("INSERT INTO scrapes (timestamp) VALUES (?)", (timestamp,))
    return cursor.lastrowid


def insert_new_change(cursor: sqlite3.Cursor, scrape_id: int) -> int:
    cursor.execute("INSERT INTO _changes (id) VALUES (?)", (None,))
    change_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO changes (id, scrape_id) VALUES (?, ?)", (change_id, scrape_id)
    )
    return change_id


def insert_with_change(
    cursor: sqlite3.Cursor,
    scrape_id: int,
    table: str,
    row: Mapping[str, Union[None, int, str]],
) -> None:
    """Insert a new row into table. If an equal row exists already, associate
    its change_id with the current scrape_id, otherwise create and associate a
    new change_id.
    """

    cols = []  # type: List[str]
    args = ()  # type: Tuple[Union[None, int, str], ...]
    for col, val in row.items():
        cols.append(col)
        args += (val,)
    assert cols

    # equal row exists...
    for (change_id,) in cursor.execute(
        f"SELECT change_id FROM {table} WHERE {'=? AND '.join(cols)}=? LIMIT 1",
        args,
    ):
        cursor.execute(
            "INSERT INTO changes (id, scrape_id) VALUES (?, ?)",
            (change_id, scrape_id),
        )
        return

    # ...otherwise insert with a new change_id
    change_id = insert_new_change(cursor, scrape_id)
    cols.append("change_id")
    args += (change_id,)
    cursor.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(args))})",
        args,
    )


def gen_title_info_data(
    scrape: ScrapedTitle,
) -> Iterator[Mapping[str, Union[int, str]]]:
    """Generate rows to insert into title_info."""

    for key in (
        "title",
        "original_title",
        "rating",
        "rating_count",
        "year",
        "duration",
    ):
        if key in scrape:
            yield {
                "title_id": scrape["id"],
                "key": key,
                "value": scrape[key],  # type: ignore
            }
    for lang in scrape.get("languages") or []:
        yield {"title_id": scrape["id"], "key": "language", "value": lang}


async def store_scraped_title(
    shared_conn: SharedConnection, scrape: ScrapedTitle
) -> None:
    async with shared_conn as cursor:
        scrape_id = insert_new_scrape(cursor, scrape["timestamp"])
        for row in gen_title_info_data(scrape):
            insert_with_change(cursor, scrape_id, "title_info", row)
        for person_id, name in scrape.get("cast") or []:
            insert_with_change(
                cursor,
                scrape_id,
                "people_info",
                {
                    "person_id": person_id,
                    "key": "name",
                    "value": name,
                },
            )
            insert_with_change(
                cursor,
                scrape_id,
                "credits",
                {
                    "title_id": scrape["id"],
                    "credit_type": "actor",
                    "person_id": person_id,
                },
            )


async def store_scraped_person(
    shared_conn: SharedConnection, scrape: ScrapedPerson
) -> None:
    async with shared_conn as cursor:
        scrape_id = insert_new_scrape(cursor, scrape["timestamp"])

        for key in ("name", "birthday"):
            if key in scrape:
                insert_with_change(
                    cursor,
                    scrape_id,
                    "people_info",
                    {
                        "person_id": scrape["id"],
                        "key": key,
                        "value": scrape[key],  # type: ignore
                    },
                )

        for title_id, credit in (scrape.get("filmography") or {}).items():
            # actual credit
            credit_types = credit["credit_type"]  # type: Sequence[Optional[str]]
            for credit_type in credit_types or [None]:
                insert_with_change(
                    cursor,
                    scrape_id,
                    "credits",
                    {
                        "title_id": title_id,
                        "credit_type": credit_type,
                        "person_id": scrape["id"],
                    },
                )

            # credit tags
            for tag in credit["tags"]:
                insert_with_change(
                    cursor,
                    scrape_id,
                    "credit_tags",
                    {
                        "title_id": title_id,
                        "person_id": scrape["id"],
                        "tag": tag,
                    },
                )

            # title_info
            title_info = {
                "id": title_id,
                "timestamp": -1,
            }  # type: ScrapedTitle
            for key in ("title", "year"):
                if credit["title_info"].get(key) is not None:
                    title_info[key] = credit["title_info"][key]  # type: ignore
            for row in gen_title_info_data(title_info):
                insert_with_change(cursor, scrape_id, "title_info", row)

            # title tags
            for tag in credit["title_info"]["tags"]:
                insert_with_change(
                    cursor,
                    scrape_id,
                    "title_tags",
                    {
                        "title_id": title_id,
                        "tag": tag,
                    },
                )
