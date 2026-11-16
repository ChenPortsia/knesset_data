"""The survey of unloaded API tables, against a made-up API."""

from ingestion.survey import survey


class FakeApi:
    def json(self, path: str, params: dict[str, str]) -> dict:
        if params.get("$top") == "0":
            return {"@odata.count": 1234}
        if path == "KNS_Broken":
            raise OSError("access denied")
        return {
            "value": [
                {"Id": 9, "BillID": 1, "GroupTypeDesc": "דברי הסבר", "ApplicationDesc": "DOCX"}
            ]
        }


def test_a_table_is_described_by_count_columns_kinds_and_a_row():
    section = survey(FakeApi(), "KNS_DocumentBill")
    assert "Rows: 1,234" in section
    assert "`Id`, `BillID`, `GroupTypeDesc`, `ApplicationDesc`" in section
    assert "דברי הסבר (1)" in section and "DOCX (1)" in section


def test_a_table_that_cannot_be_read_is_reported_not_fatal():
    class Broken(FakeApi):
        def json(self, path: str, params: dict[str, str]) -> dict:
            raise OSError("access denied")

    assert "Could not be read: OSError: access denied" in survey(Broken(), "KNS_Bill")
