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

import typing  # _UnionGenericAlias
from typing import List, Mapping, Tuple, TypedDict, Union


def schema_from_typing(t):  # type: ignore
    if t == str:
        return {"type": "string"}
    elif t == int:
        return {"type": "number"}
    elif hasattr(t, "__annotations__"):
        s = {
            "type": "object",
            "required": [],
            "properties": {},
        }
        for k, kt in t.__annotations__.items():
            s["properties"][k] = schema_from_typing(kt)
        s["required"] = list(t.__required_keys__)
        return s
    elif getattr(t, "_name", None) == "Tuple":
        return {
            "type": "array",
            "prefixItems": [schema_from_typing(at) for at in t.__args__],
            "items": False,
        }
    elif getattr(t, "_name", None) == "List":
        return {
            "type": "array",
            "items": schema_from_typing(t.__args__[0]),
        }
    elif getattr(t, "_name", None) == "Mapping":
        assert t.__args__[0] == str, repr(t)
        return {
            "type": "object",
            "additionalProperties": schema_from_typing(t.__args__[1]),
        }
    elif isinstance(t, typing._UnionGenericAlias):
        return {
            "oneOf": [schema_from_typing(at) for at in t.__args__],
        }
    else:
        raise NotImplementedError(repr(t))


CastMember = Tuple[str, str]


class _ScrapedTitle(TypedDict):
    id: str
    timestamp: int


class ScrapedTitle(_ScrapedTitle, total=False):
    title: str
    original_title: str
    rating: str
    rating_count: int
    year: str
    directors: List[CastMember]
    writers: List[CastMember]
    cast: List[CastMember]
    duration: int
    languages: List[str]


class FilmCreditTitleInfo(TypedDict, total=False):
    title: str
    year: str
    tags: List[str]


class FilmCredit(TypedDict):
    id: str
    credit_type: List[str]
    tags: List[str]
    title_info: FilmCreditTitleInfo


Filmography = Mapping[str, FilmCredit]


class _ScrapedPerson(TypedDict):
    id: str
    timestamp: int


class ScrapedPerson(_ScrapedPerson, total=False):
    name: str
    birthday: str
    filmography: Filmography


class ScrapeResultTitle(TypedDict):
    title: ScrapedTitle


class ScrapeResultPerson(TypedDict):
    person: ScrapedPerson


ScrapeResult = Union[ScrapeResultTitle, ScrapeResultPerson]
