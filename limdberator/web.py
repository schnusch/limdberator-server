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

import argparse
import asyncio
import re
import socket
import sqlite3
from typing import List, Optional, Tuple, Union, cast

import jsonschema  # type: ignore
from aiohttp import web
from aiohttp.web_runner import AppRunner, BaseSite, SockSite, TCPSite, UnixSite

from .types import (
    ScrapeResult,
    ScrapeResultTitle,
    ScrapeResultPerson,
    schema_from_typing,
)
from .database import (
    SharedConnection,
    init_database,
    store_scraped_person,
    store_scraped_title,
)

try:
    import systemd.daemon  # type: ignore
except ImportError:
    systemd_imported = False

    def get_systemd_listen_sockets() -> List[socket.socket]:
        raise NotImplementedError

else:
    systemd_imported = True

    def get_systemd_listen_sockets() -> List[socket.socket]:
        socks = []
        for fd in systemd.daemon.listen_fds():
            for family in (socket.AF_UNIX, socket.AF_INET, socket.AF_INET6):
                if systemd.daemon.is_socket(
                    fd, family=family, type=socket.SOCK_STREAM, listening=True
                ):
                    sock = socket.fromfd(fd, family, socket.SOCK_STREAM)
                    socks.append(sock)
                    break
            else:
                raise RuntimeError(
                    "socket family must be AF_INET, AF_INET6, or AF_UNIX; "
                    "socket type must be SOCK_STREAM; and it must be listening"
                )
        return socks


scrape_result_schema = schema_from_typing(ScrapeResult)  # type: ignore


def create_app(shared_conn: SharedConnection) -> web.Application:
    routes = web.RouteTableDef()

    @routes.post("/")
    async def post(request: web.Request) -> web.Response:
        data = await request.json()
        try:
            jsonschema.validate(data, scrape_result_schema)
        except jsonschema.exceptions.ValidationError as e:
            raise web.HTTPBadRequest(text="400 Bad Request\n\n" + e.message)
        scrape = cast(ScrapeResult, data)
        if "title" in scrape:
            await store_scraped_title(
                shared_conn, cast(ScrapeResultTitle, scrape)["title"]
            )
        elif "person" in scrape:
            await store_scraped_person(
                shared_conn, cast(ScrapeResultPerson, scrape)["person"]
            )
        else:
            raise RuntimeError("should be unreachable")
        raise web.HTTPNoContent

    app = web.Application()
    app.add_routes(routes)
    return app


ListenAddress = Union[str, Tuple[str, int], socket.socket]


def listen_address(arg: str) -> ListenAddress:
    socket = r"(?P<socket>.*/.*)"
    ipv6 = r"\[(?P<ipv6>.*)\]"
    host = r"(?P<host>.*)"
    port = r":(?P<port>\d+)"
    m = re.match(f"^(?:{socket}|(?:(?:{ipv6}|{host}){port}))$", arg)
    if m is None:
        raise ValueError
    if m["port"]:
        portnum = int(m["port"], 10)
        host = m["ipv6"] or m["host"]
        return (host, portnum)
    else:
        return m["socket"]


async def real_main(database: str, listen_addresses: List[ListenAddress]) -> None:
    assert listen_addresses
    with sqlite3.connect(database) as conn:
        init_database(conn.cursor())
        shared_conn = SharedConnection(conn)

        app = create_app(shared_conn)
        runner = AppRunner(app)
        await runner.setup()
        try:
            sites = []  # type: List[BaseSite]
            for address in listen_addresses:
                if isinstance(address, socket.socket):
                    sites.append(SockSite(runner, address))
                elif isinstance(address, str):
                    sites.append(UnixSite(runner, address))
                else:
                    host, port = address
                    sites.append(TCPSite(runner, host, port))
            for site in sites:
                await site.start()

            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(
        description="Receive and store data scraped by LIMDberator",
        epilog=None
        if systemd_imported
        else "systemd socket activations cannot be used, because systemd.daemon could not be imported, see https://github.com/systemd/python-systemd",
    )
    p.add_argument(
        "-d", "--database", required=True, help="path to the SQLite database file"
    )
    g = p.add_mutually_exclusive_group(required=True)
    if systemd_imported:
        g.add_argument(
            "--systemd",
            action="store_true",
            help="receive listening sockets from systemd",
        )
    g.add_argument(
        "-l", "--listen", type=listen_address, action="append", help="listening address"
    )
    args = p.parse_args(argv)

    if systemd_imported and args.systemd:
        listen = cast(List[ListenAddress], get_systemd_listen_sockets())
        if not listen:
            p.error("no sockets received from systemd")
    else:
        listen = args.listen

    asyncio.run(real_main(args.database, listen))
