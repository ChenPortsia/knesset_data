"""Chunking: short turns are merged, long ones split, and nothing said is lost."""

from nlp.chunk import MAX_WORDS, OVERLAP_WORDS, Turn, chunk_session, split_long, to_row


def turn(index: int, words: int, speaker: str = "א", person_id: int | None = None) -> Turn:
    return Turn(index, speaker, person_id, " ".join(f"w{index}_{i}" for i in range(words)))


def test_short_turns_are_merged_up_to_the_limit_and_keep_their_order():
    chunks = chunk_session([turn(i, 50) for i in range(10)])
    assert all(c.words <= MAX_WORDS + 10 for c in chunks)  # + the speaker names
    assert [(c.first_turn, c.last_turn) for c in chunks] == [(0, 3), (4, 7), (8, 9)]


def test_a_chunk_lists_its_speakers_and_linked_people_once():
    chunks = chunk_session([turn(0, 5, "גפני", 1), turn(1, 5, "אורח"), turn(2, 5, "גפני", 1)])
    assert len(chunks) == 1
    assert chunks[0].speakers == ["גפני", "אורח"] and chunks[0].person_ids == [1]
    assert chunks[0].lines[1].startswith("אורח: w1_0")


def test_a_long_turn_is_split_into_overlapping_pieces_of_its_own():
    chunks = chunk_session([turn(0, 10), turn(1, 500), turn(2, 10)])
    assert [(c.first_turn, c.last_turn, c.part) for c in chunks] == [
        (0, 0, 0), (1, 1, 0), (1, 1, 1), (1, 1, 2), (2, 2, 0),
    ]  # fmt: skip
    first, second = chunks[1].lines[0].split()[1:], chunks[2].lines[0].split()[1:]
    assert second[:OVERLAP_WORDS] == first[-OVERLAP_WORDS:]


def test_no_word_of_a_split_text_is_lost():
    text = ". ".join(" ".join(f"s{s}w{w}" for w in range(40)) for s in range(30))
    pieces = split_long(text)
    assert all(len(p.split()) <= MAX_WORDS + OVERLAP_WORDS for p in pieces)
    assert set(text.split()) == {word for p in pieces for word in p.split()}


def test_a_row_starts_with_where_and_when():
    session = {
        "committee_session_id": 7, "committee_id": 2, "knesset_num": 25,
        "session_date": "2024-11-12", "committee_name": "ועדת הכספים",
    }  # fmt: skip
    row = to_row(session, chunk_session([turn(3, 5, "גפני", 1)])[0])
    assert row["chunk_id"] == "7-3-0"
    assert row["chunk_text"].startswith("ועדת הכספים · 2024-11-12\nגפני: w3_0")
    assert row["person_ids"] == [1] and row["words"] == 6
