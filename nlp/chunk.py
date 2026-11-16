"""Cut committee turns into chunks: the pieces of text that are searched.

Turns are short (half are a few words), so a chunk is a run of consecutive turns from one
session, up to MAX_WORDS, written as a dialogue: one "speaker: text" line per turn. A turn
longer than that is split at sentence ends, each piece carrying the end of the one before.
Every chunk starts with a line saying where and when, so its embedding knows the setting.
"""

import re
from dataclasses import dataclass, field
from typing import Any

MAX_WORDS = 220  # about 400 tokens of Hebrew: what the embedding model reads well
OVERLAP_WORDS = 30  # a split turn repeats this much, so a sentence cut in two is still found
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Turn:
    turn_index: int
    speaker_name: str
    person_id: int | None
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Chunk:
    first_turn: int
    last_turn: int
    part: int  # 0, or the piece number of a turn that was split
    lines: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    person_ids: list[int] = field(default_factory=list)

    def add(self, turn: Turn, text: str) -> None:
        self.lines.append(f"{turn.speaker_name}: {text}")
        self.last_turn = turn.turn_index
        if turn.speaker_name not in self.speakers:
            self.speakers.append(turn.speaker_name)
        if turn.person_id is not None and turn.person_id not in self.person_ids:
            self.person_ids.append(turn.person_id)

    @property
    def words(self) -> int:
        return sum(len(line.split()) for line in self.lines)


def split_long(text: str) -> list[str]:
    """Pieces of at most MAX_WORDS, cut at sentence ends, each starting with the last
    OVERLAP_WORDS of the one before. A sentence longer than MAX_WORDS is cut by words."""
    sentences: list[str] = []
    for sentence in SENTENCE_END.split(text):
        words = sentence.split()
        sentences += [" ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]
    pieces: list[list[str]] = [[]]
    for sentence in sentences:
        words = sentence.split()
        if pieces[-1] and len(pieces[-1]) + len(words) > MAX_WORDS:
            pieces.append(pieces[-1][-OVERLAP_WORDS:])
        pieces[-1] += words
    return [" ".join(piece) for piece in pieces if piece]


def chunk_session(turns: list[Turn]) -> list[Chunk]:
    """The chunks of one session's turns, in order. No turn is dropped."""
    chunks: list[Chunk] = []
    current: Chunk | None = None
    for turn in turns:
        if turn.words > MAX_WORDS:  # a long speech: its own chunks
            for part, piece in enumerate(split_long(turn.text)):
                chunks.append(Chunk(turn.turn_index, turn.turn_index, part))
                chunks[-1].add(turn, piece)
            current = None
            continue
        if current is None or current.words + turn.words > MAX_WORDS:
            current = Chunk(turn.turn_index, turn.turn_index, 0)
            chunks.append(current)
        current.add(turn, turn.text)
    return chunks


def to_row(session: dict[str, Any], chunk: Chunk) -> dict[str, Any]:
    """A chunk as a row of rag.chunks, with its where-and-when line on top."""
    header = f"{session['committee_name']} · {session['session_date']}"
    return {
        "chunk_id": f"{session['committee_session_id']}-{chunk.first_turn}-{chunk.part}",
        "committee_session_id": session["committee_session_id"],
        "committee_id": session["committee_id"],
        "knesset_num": session["knesset_num"],
        "session_date": session["session_date"],
        "first_turn": chunk.first_turn,
        "last_turn": chunk.last_turn,
        "speakers": chunk.speakers,
        "person_ids": chunk.person_ids,
        "words": chunk.words,
        "chunk_text": header + "\n" + "\n".join(chunk.lines),
    }
