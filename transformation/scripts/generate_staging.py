"""Generate the dbt staging models for the OData tables: SQL and bilingual YAML.

Writes models/1_staging/odata/: one stg_odata__<entity>.sql per table, plus
_odata__sources.yml and _odata__models.yml with English | Hebrew descriptions.
It overwrites those files, so change the spec below and rerun rather than editing
the generated files by hand (or stop using this script once models diverge).

Column types come from the API's $metadata; the SQL follows the project style:
uppercase, every column cast, CTEs in the order source -> renamed -> filtered -> enhanced.

Run from the repo root:
    make staging-models
    uv run python transformation/scripts/generate_staging.py --metadata saved_metadata.xml
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from dlt.common.normalizers.naming.snake_case import NamingConvention

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # to reuse ingestion's API client and settings
OUT = ROOT / "transformation" / "models" / "1_staging" / "odata"

# fmt: off

# Shared column descriptions: name -> (English, Hebrew)
COMMON = {
    "knesset_num": ("Knesset number (e.g. 25)", "מספר הכנסת (למשל 25)"),
    "updated_at": ("When the source row last changed (LastUpdatedDate)", "מועד העדכון האחרון של השורה במקור"),
    "is_current": ("True if this is current (serving now)", "האם בתוקף כעת"),
    "start_at": ("Start, Israel local time", "מועד התחלה, שעון ישראל"),
    "finish_at": ("End, Israel local time; null if ongoing", "מועד סיום, שעון ישראל; ריק אם עדיין פעיל"),
    "person_id": ("Person ID (see stg_odata__person)", "מזהה אדם"),
    "committee_id": ("Committee ID (see stg_odata__committee)", "מזהה ועדה"),
    "status_id": ("Status ID (see stg_odata__status)", "מזהה סטטוס"),
    "item_id": ("ID of the discussed item (bill, query, agenda...), by item type", "מזהה הפריט הנדון (הצעת חוק, שאילתה, הצעה לסדר...)"),
    "item_type_id": ("Item type ID (see stg_odata__item_type)", "מזהה סוג הפריט"),
    "ordinal": ("Order within the parent", "מספר סידורי"),
    "plenum_session_id": ("Plenum session ID", "מזהה ישיבת מליאה"),
    "committee_session_id": ("Committee session ID", "מזהה ישיבת ועדה"),
}

# model: (source table, English, Hebrew, grain, [(column, source expression or None, en, he)])
# Plain column names reuse COMMON descriptions; expressions use macros:
#   local_time(col)  -> Israel local timestamp
#   code_label(domain, col) -> English label from the code_labels seed
MODELS = {
    "person": ("kns_person", "People: MKs, ministers and other office holders", "אנשים: חברי כנסת, שרים ונושאי תפקידים", "one row per person", [
        ("person_id", "id", "Person ID", "מזהה אדם"),
        ("first_name", "trim(first_name)", "First name (Hebrew)", "שם פרטי"),
        ("last_name", "trim(last_name)", "Last name (Hebrew)", "שם משפחה"),
        ("gender_id", "gender_id", "Gender code: 250 female, 251 male", "קוד מגדר"),
        ("gender_he", "gender_desc", "Gender in Hebrew", "מגדר בעברית"),
        ("email", "email", "Knesset email address", "כתובת דוא\"ל בכנסת"),
        ("is_current", "is_current", "True if serving in the current Knesset", "האם מכהן בכנסת הנוכחית"),
        "updated_at",
    ]),
    "position": ("kns_position", "Position types (MK, minister, committee chair...)", "סוגי תפקידים (ח\"כ, שר, יו\"ר ועדה...)", "one row per position type", [
        ("position_id", "id", "Position ID", "מזהה תפקיד"),
        ("position_name", "description", "Position name (Hebrew)", "שם התפקיד"),
        ("gender_id", "gender_id", "Gender the title form applies to", "המגדר שאליו מתייחס נוסח התפקיד"),
        "updated_at",
    ]),
    "person_position": ("kns_person_to_position", "Who held which position, when: MK in a faction, minister, committee member", "מי כיהן באיזה תפקיד ומתי: ח\"כ בסיעה, שר, חבר ועדה", "one row per person, position and period", [
        ("person_position_id", "id", "Person-position row ID", "מזהה שורת תפקיד"),
        "person_id",
        ("position_id", "position_id", "Position ID (see stg_odata__position)", "מזהה תפקיד"),
        "knesset_num",
        ("faction_id", "faction_id", "Faction the person belonged to in this period", "הסיעה שאליה השתייך בתקופה זו"),
        ("faction_name", "faction_name", "Faction name (Hebrew)", "שם הסיעה"),
        "committee_id",
        ("committee_name", "committee_name", "Committee name (Hebrew)", "שם הוועדה"),
        ("ministry_id", "gov_ministry_id", "Government ministry ID", "מזהה משרד ממשלתי"),
        ("ministry_name", "gov_ministry_name", "Government ministry name (Hebrew)", "שם המשרד הממשלתי"),
        ("government_num", "government_num", "Government number", "מספר הממשלה"),
        ("duty", "duty_desc", "Duty description (Hebrew)", "תיאור התפקיד"),
        ("start_at", "{{ local_time('start_date') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('finish_date') }}", *COMMON["finish_at"]),
        "is_current",
        "updated_at",
    ]),
    "faction": ("kns_faction", "Factions (parliamentary groups) per Knesset", "סיעות בכל כנסת", "one row per faction per Knesset", [
        ("faction_id", "id", "Faction ID", "מזהה סיעה"),
        ("faction_name", "trim(name)", "Faction name (Hebrew)", "שם הסיעה"),
        "knesset_num",
        ("start_at", "{{ local_time('start_date') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('finish_date') }}", *COMMON["finish_at"]),
        "is_current",
        "updated_at",
    ]),
    "knesset_period": ("kns_knesset_dates", "Knesset terms split into assemblies and sittings", "כנסות לפי כנסים ומושבים", "one row per Knesset sitting period", [
        ("knesset_period_id", "id", "Period ID", "מזהה תקופה"),
        "knesset_num",
        ("knesset_name", "name", "Knesset name (Hebrew)", "שם הכנסת"),
        ("assembly", "assembly", "Assembly number within the Knesset", "מספר הכנס"),
        ("plenum", "plenum", "Sitting (winter/summer) number within the assembly", "מספר המושב"),
        ("start_at", "{{ local_time('plenum_start') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('plenum_finish') }}", *COMMON["finish_at"]),
        "is_current",
        "updated_at",
    ]),
    "ministry": ("kns_gov_ministry", "Government ministries", "משרדי ממשלה", "one row per ministry", [
        ("ministry_id", "id", "Ministry ID", "מזהה משרד"),
        ("ministry_name", "trim(name)", "Ministry name (Hebrew)", "שם המשרד"),
        ("category_id", "category_id", "Ministry category ID", "מזהה קטגוריה"),
        ("category_name", "category_name", "Ministry category (Hebrew)", "קטגוריה"),
        ("gov_id", "gov_id", "Government ID in the source", "מזהה ממשלה במקור"),
        ("is_active", "is_active", "True if the ministry exists today", "האם המשרד פעיל"),
        "updated_at",
    ]),
    "committee": ("kns_committee", "Knesset committees per Knesset", "ועדות הכנסת בכל כנסת", "one row per committee per Knesset", [
        ("committee_id", "id", "Committee ID", "מזהה ועדה"),
        ("committee_name", "trim(name)", "Committee name (Hebrew)", "שם הוועדה"),
        "knesset_num",
        ("category_id", "category_id", "Committee category ID (same committee across Knessets)", "מזהה קטגוריית ועדה (אותה ועדה לאורך כנסות)"),
        ("category_name", "category_desc", "Committee category (Hebrew)", "קטגוריית הוועדה"),
        ("committee_type_id", "committee_type_id", "Committee type ID", "מזהה סוג ועדה"),
        ("committee_type", "committee_type_desc", "Committee type: main, sub, joint... (Hebrew)", "סוג ועדה: ראשית, משנה, משותפת..."),
        ("additional_type_id", "NULLIF(additional_type_id, -1)", "Additional type ID; null if none (the source uses -1)", "מזהה סוג נוסף"),
        ("additional_type", "additional_type_desc", "Additional type: permanent, special... (Hebrew)", "סוג נוסף: קבועה, מיוחדת..."),
        ("parent_committee_id", "parent_committee_id", "Parent committee for subcommittees", "ועדת אם (לוועדות משנה)"),
        ("parent_committee_name", "committee_parent_name", "Parent committee name (Hebrew)", "שם ועדת האם"),
        ("start_at", "{{ local_time('start_date') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('finish_date') }}", *COMMON["finish_at"]),
        "is_current",
        "updated_at",
    ]),
    "committee_session": ("kns_committee_session", "Committee sessions (meetings)", "ישיבות ועדה", "one row per committee session", [
        ("committee_session_id", "id", "Committee session ID", "מזהה ישיבת ועדה"),
        "committee_id",
        "knesset_num",
        ("session_number", "number", "Session number within the committee", "מספר הישיבה בוועדה"),
        ("session_type_id", "type_id", "Session type ID", "מזהה סוג ישיבה"),
        ("session_type", "type_desc", "Session type: open / closed (Hebrew)", "סוג ישיבה: פתוחה / חסויה"),
        "status_id",
        ("status", "status_desc", "Session status (Hebrew)", "סטטוס הישיבה"),
        ("location", "location", "Room or place", "מקום הישיבה"),
        ("session_url", "session_url", "Session page on the Knesset site", "קישור לעמוד הישיבה"),
        ("broadcast_url", "broadcast_url", "Video broadcast link", "קישור לשידור"),
        ("note", "note", "Free-text note", "הערה"),
        ("start_at", "{{ local_time('start_date') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('finish_date') }}", *COMMON["finish_at"]),
        "updated_at",
    ]),
    "committee_session_item": ("kns_cmt_session_item", "Items on a committee session agenda (bills, queries, topics); all Knessets", "פריטים בסדר היום של ישיבת ועדה; כל הכנסות", "one row per item per committee session", [
        ("session_item_id", "id", "Session item ID", "מזהה פריט בישיבה"),
        "committee_session_id",
        "item_id",
        "item_type_id",
        ("item_name", "name", "Item title (Hebrew)", "כותרת הפריט"),
        "ordinal",
        "status_id",
        "updated_at",
    ]),
    "plenum_session": ("kns_plenum_session", "Plenum sessions", "ישיבות מליאה", "one row per plenum session", [
        ("plenum_session_id", "id", "Plenum session ID", "מזהה ישיבת מליאה"),
        "knesset_num",
        ("session_number", "number", "Session number", "מספר הישיבה"),
        ("session_name", "name", "Session title (Hebrew)", "כותרת הישיבה"),
        ("is_special_meeting", "is_special_meeting", "True for a special (extra) session", "האם ישיבה מיוחדת"),
        ("start_at", "{{ local_time('start_date') }}", *COMMON["start_at"]),
        ("finish_at", "{{ local_time('finish_date') }}", *COMMON["finish_at"]),
        "updated_at",
    ]),
    "plenum_session_item": ("kns_plm_session_item", "Items on a plenum session agenda; all Knessets", "פריטים בסדר היום של ישיבת מליאה; כל הכנסות", "one row per item per plenum session", [
        ("session_item_id", "id", "Session item ID", "מזהה פריט בישיבה"),
        "plenum_session_id",
        "item_id",
        "item_type_id",
        ("item_type", "item_type_desc", "Item type (Hebrew)", "סוג הפריט"),
        ("item_name", "name", "Item title (Hebrew)", "כותרת הפריט"),
        "ordinal",
        "status_id",
        ("is_discussion", "is_discussion", "True if the item was discussed (not only listed)", "האם הפריט נדון"),
        "updated_at",
    ]),
    "bill": ("kns_bill", "Bills (proposed laws)", "הצעות חוק", "one row per bill", [
        ("bill_id", "id", "Bill ID", "מזהה הצעת חוק"),
        "knesset_num",
        ("bill_name", "trim(name)", "Bill title (Hebrew)", "שם הצעת החוק"),
        ("bill_type_id", "type_id", "Bill type ID", "מזהה סוג הצעה"),
        ("bill_type", "type_desc", "Bill type (Hebrew)", "סוג ההצעה"),
        ("origin_id", "sub_type_id", "Origin code: 53 government, 54 private, 55 committee", "קוד מקור ההצעה"),
        ("origin_he", "sub_type_desc", "Origin in Hebrew", "מקור ההצעה בעברית"),
        ("private_number", "private_number", "Number of a private bill", "מספר הצעת חוק פרטית"),
        ("bill_number", "number", "Bill number", "מספר הצעת החוק"),
        ("committee_id", "NULLIF(committee_id, -1)", "Committee that prepared the bill; null if none (the source uses -1)", "הוועדה שהכינה את ההצעה"),
        ("status_id", "status_id", "Current stage of the bill (see stg_odata__status)", "השלב הנוכחי של ההצעה"),
        ("postponement_reason_id", "postponement_reason_id", "Why the bill was stopped", "מזהה סיבת עצירה"),
        ("postponement_reason", "postponement_reason_desc", "Why the bill was stopped (Hebrew)", "סיבת עצירה"),
        ("is_continuation_bill", "is_continuation_bill", "True if continued from a previous Knesset", "האם הצעה בדין רציפות"),
        ("published_at", "{{ local_time('publication_date') }}", "Publication date in Reshumot", "מועד פרסום ברשומות"),
        ("publication_series_id", "publication_series_id", "Publication series ID", "מזהה סדרת פרסום"),
        ("publication_series", "publication_series_desc", "Publication series (Hebrew)", "סדרת פרסום"),
        ("first_call_series_id", "publication_series_first_call_id", "Publication series of the first reading", "סדרת פרסום לקריאה ראשונה"),
        ("first_call_series", "publication_series_first_call_desc", "First reading publication series (Hebrew)", "סדרת פרסום לקריאה ראשונה"),
        ("magazine_number", "magazine_number", "Gazette issue number", "מספר חוברת"),
        ("page_number", "page_number", "Gazette page", "מספר עמוד"),
        ("summary", "summary_law", "Short summary of the law (Hebrew)", "תקציר החוק"),
        "updated_at",
    ]),
    "bill_initiator": ("kns_bill_initiator", "MKs who initiated or joined a bill; all Knessets", "חברי כנסת שיזמו או הצטרפו להצעת חוק; כל הכנסות", "one row per bill and person", [
        ("bill_initiator_id", "id", "Row ID", "מזהה שורה"),
        ("bill_id", "bill_id", "Bill ID", "מזהה הצעת חוק"),
        "person_id",
        ("is_initiator", "is_initiator", "True for an initiator, false for a joiner", "יוזם (אמת) או מצטרף (שקר)"),
        "ordinal",
        "updated_at",
    ]),
    "law": ("kns_israel_law", "Israeli laws in force or repealed; all Knessets", "חוקי מדינת ישראל; כל הכנסות", "one row per law", [
        ("law_id", "id", "Law ID", "מזהה חוק"),
        ("knesset_num", "knesset_num", "Knesset that passed the law", "הכנסת שחוקקה את החוק"),
        ("law_name", "trim(name)", "Law name (Hebrew)", "שם החוק"),
        ("is_basic_law", "is_basic_law", "True for a Basic Law", "האם חוק יסוד"),
        ("is_favorite_law", "is_favorite_law", "True if featured by the Knesset site", "האם חוק מועדף באתר"),
        ("is_budget_law", "is_budget_law", "True for a budget law", "האם חוק תקציב"),
        ("validity_id", "law_validity_id", "Validity status ID", "מזהה תוקף"),
        ("validity", "law_validity_desc", "Validity status: in force, repealed... (Hebrew)", "תוקף החוק"),
        ("published_at", "{{ local_time('publication_date') }}", "First publication date", "מועד פרסום ראשון"),
        ("latest_published_at", "{{ local_time('latest_publication_date') }}", "Latest amendment publication date", "מועד פרסום אחרון"),
        ("valid_from", "{{ local_time('validity_start_date') }}", "In force from", "בתוקף מ-"),
        ("valid_from_notes", "validity_start_date_notes", "Notes on start of validity", "הערות לתחילת תוקף"),
        ("valid_until", "{{ local_time('validity_finish_date') }}", "In force until", "בתוקף עד"),
        ("valid_until_notes", "validity_finish_date_notes", "Notes on end of validity", "הערות לסיום תוקף"),
        "updated_at",
    ]),
    "plenum_vote": ("kns_plenum_vote", "Plenum votes (one per vote held)", "הצבעות במליאה", "one row per vote", [
        ("vote_id", "id", "Vote ID", "מזהה הצבעה"),
        ("plenum_session_id", "session_id", *COMMON["plenum_session_id"]),
        "item_id",
        "ordinal",
        ("voted_at", "{{ local_time('vote_date_time') }}", "When the vote took place, Israel local time", "מועד ההצבעה, שעון ישראל"),
        ("vote_title", "vote_title", "Vote title, usually the bill or motion (Hebrew)", "כותרת ההצבעה"),
        ("vote_subject", "vote_subject", "What was voted on, e.g. first reading (Hebrew)", "נושא ההצבעה, למשל קריאה ראשונה"),
        ("vote_method_id", "vote_method_id", "Voting method ID", "מזהה שיטת הצבעה"),
        ("vote_method", "vote_method_desc", "Voting method (Hebrew)", "שיטת הצבעה"),
        ("vote_status_id", "vote_status_code", "Vote status ID", "מזהה סטטוס הצבעה"),
        ("vote_status", "vote_status_desc", "Vote status (Hebrew)", "סטטוס הצבעה"),
        ("is_no_confidence", "is_no_confidence_in_gov", "True for a no-confidence vote", "האם הצבעת אי-אמון"),
        ("for_option_id", "for_option_id", "Meaning of a 'for' vote, ID", "מזהה משמעות הצבעה בעד"),
        ("for_option", "for_option_desc", "Meaning of a 'for' vote (Hebrew)", "משמעות הצבעה בעד"),
        ("against_option_id", "against_option_id", "Meaning of an 'against' vote, ID", "מזהה משמעות הצבעה נגד"),
        ("against_option", "against_option_desc", "Meaning of an 'against' vote (Hebrew)", "משמעות הצבעה נגד"),
        "updated_at",
    ]),
    "plenum_vote_result": ("kns_plenum_vote_result", "How each MK voted in each plenum vote", "איך הצביע כל ח\"כ בכל הצבעה במליאה", "one row per vote and MK", [
        ("vote_result_id", "id", "Row ID", "מזהה שורה"),
        ("vote_id", "vote_id", "Vote ID (see stg_odata__plenum_vote)", "מזהה הצבעה"),
        ("person_id", "mk_id", "MK who voted", "חבר הכנסת המצביע"),
        ("plenum_session_id", "session_id", *COMMON["plenum_session_id"]),
        "item_id",
        ("voted_at", "{{ local_time('vote_date') }}", "When the vote took place, Israel local time", "מועד ההצבעה, שעון ישראל"),
        ("result_code", "result_code", "Result code: 7 for, 8 against, 9 abstain, 10 absent, 11 secret ballot", "קוד תוצאה"),
        ("result_he", "result_desc", "Result in Hebrew", "תוצאה בעברית"),
        "updated_at",
    ]),
    "query": ("kns_query", "Parliamentary queries from MKs to ministers", "שאילתות של חברי כנסת לשרים", "one row per query", [
        ("query_id", "id", "Query ID", "מזהה שאילתה"),
        "knesset_num",
        ("query_number", "number", "Query number", "מספר שאילתה"),
        ("query_name", "trim(name)", "Query title (Hebrew)", "כותרת השאילתה"),
        ("query_type_id", "type_id", "Query type ID", "מזהה סוג שאילתה"),
        ("query_type", "type_desc", "Query type: regular, direct, urgent (Hebrew)", "סוג שאילתה: רגילה, ישירה, דחופה"),
        "status_id",
        ("person_id", "person_id", "MK who asked", "חבר הכנסת השואל"),
        ("ministry_id", "gov_ministry_id", "Ministry asked", "המשרד הנשאל"),
        ("submitted_at", "{{ local_time('submit_date') }}", "When submitted", "מועד הגשה"),
        ("reply_planned_at", "{{ local_time('reply_date_planned') }}", "Planned reply date", "מועד תשובה מתוכנן"),
        ("replied_at", "{{ local_time('reply_minister_date') }}", "When the minister replied", "מועד תשובת השר"),
        "updated_at",
    ]),
    "agenda": ("kns_agenda", "Motions for the agenda", "הצעות לסדר היום", "one row per motion", [
        ("agenda_id", "id", "Motion ID", "מזהה הצעה לסדר"),
        "knesset_num",
        ("agenda_number", "number", "Motion number", "מספר ההצעה"),
        ("agenda_name", "trim(name)", "Motion title (Hebrew)", "כותרת ההצעה"),
        ("classification_id", "classification_id", "Classification ID", "מזהה סיווג"),
        ("classification", "classification_desc", "Classification: regular, urgent... (Hebrew)", "סיווג: רגילה, דחופה..."),
        ("sub_type_id", "sub_type_id", "Sub-type ID", "מזהה תת-סוג"),
        ("sub_type", "sub_type_desc", "Sub-type (Hebrew)", "תת-סוג"),
        "status_id",
        ("initiator_person_id", "initiator_person_id", "MK who proposed the motion", "חבר הכנסת המציע"),
        ("minister_person_id", "minister_person_id", "Minister who replied", "השר המשיב"),
        ("committee_id", "committee_id", "Committee the motion was sent to", "הוועדה שאליה הועברה ההצעה"),
        ("recommended_committee_id", "recommend_committee_id", "Committee recommended for the motion", "הוועדה המומלצת"),
        ("leading_agenda_id", "leading_agenda_id", "Leading motion when merged with others", "ההצעה המובילה (כשאוחדו הצעות)"),
        ("gov_recommendation_id", "gov_recommendation_id", "Government position ID", "מזהה עמדת הממשלה"),
        ("gov_recommendation", "gov_recommendation_desc", "Government position (Hebrew)", "עמדת הממשלה"),
        ("postponement_reason_id", "postopenment_reason_id", "Why the motion was stopped, ID", "מזהה סיבת עצירה"),
        ("postponement_reason", "postopenment_reason_desc", "Why the motion was stopped (Hebrew)", "סיבת עצירה"),
        ("president_decision_at", "{{ local_time('president_decision_date') }}", "Speaker's decision date", "מועד החלטת יו\"ר הכנסת"),
        "updated_at",
    ]),
    "status": ("kns_status", "Status codes for bills, queries, sessions and more", "קודי סטטוס להצעות חוק, שאילתות, ישיבות ועוד", "one row per status", [
        ("status_id", "id", "Status ID", "מזהה סטטוס"),
        ("status_name", "\"desc\"", "Status name (Hebrew)", "שם הסטטוס"),
        ("status_type_id", "type_id", "What the status applies to, ID", "מזהה סוג הסטטוס"),
        ("status_type", "type_desc", "What the status applies to: bill, query... (Hebrew)", "סוג הסטטוס: הצעת חוק, שאילתה..."),
        ("order_transition", "order_transition", "Order of the status in the process", "סדר הסטטוס בתהליך"),
        ("is_active", "is_active", "True if the status is still used", "האם הסטטוס בשימוש"),
        "updated_at",
    ]),
    "item_type": ("kns_item_type", "Types of items discussed in sessions", "סוגי פריטים הנדונים בישיבות", "one row per item type", [
        ("item_type_id", "id", "Item type ID", "מזהה סוג פריט"),
        ("item_type_name", "\"desc\"", "Item type name (Hebrew)", "שם סוג הפריט"),
        ("source_table", "table_name", "OData table that holds the items", "טבלת המקור של הפריטים"),
    ]),
}


REPLACED = {"kns_item_type"}  # fully replaced each run, no SCD2 history

# Derived columns, added in the `enhanced` CTE: model -> [(name, SQL expression, type, en, he)]
ENHANCED = {
    "person": [
        ("full_name", "first_name || ' ' || last_name", "VARCHAR", "First and last name", "שם מלא"),
        ("gender", "{{ code_label('gender', 'gender_id') }}", "VARCHAR", "Gender: female / male", "מגדר"),
    ],
    "bill": [
        ("origin", "{{ code_label('bill_origin', 'origin_id') }}", "VARCHAR",
         "Who proposed it: government / private / committee", "מקור ההצעה: ממשלתית / פרטית / ועדה"),
    ],
    "plenum_vote_result": [
        ("result", "{{ code_label('vote_result', 'result_code') }}", "VARCHAR",
         "Result: for / against / abstain / absent / voted", "תוצאה: בעד / נגד / נמנע / לא נכח / הצביע"),
    ],
}
TYPE_OVERRIDES = {("plenum_session_item", "is_discussion"): "BOOLEAN"}  # 0/1 in the source

# Column types: the OData $metadata type of each source column, as DuckDB SQL types.
SQL_TYPES = {
    "Edm.Byte": "SMALLINT", "Edm.Int16": "SMALLINT", "Edm.Int32": "INTEGER", "Edm.Int64": "BIGINT",
    "Edm.String": "VARCHAR", "Edm.Boolean": "BOOLEAN", "Edm.DateTimeOffset": "TIMESTAMPTZ",
}
EDM = "{http://docs.oasis-open.org/odata/ns/edm}"
SCD2_COLUMNS = [
    ("loaded_at", "_dlt_valid_from", "When this version of the row was loaded", "מועד טעינת הגרסה הזו של השורה"),
    ("valid_to", "_dlt_valid_to", "", ""),  # used by the filter, not in the output
]
# fmt: on


def source_types(metadata: bytes) -> dict[str, dict[str, str]]:
    """bronze table -> bronze column -> SQL type, from the $metadata XML."""
    snake = NamingConvention().normalize_identifier
    return {
        snake(entity.get("Name")): {
            snake(prop.get("Name")): SQL_TYPES[prop.get("Type")]
            for prop in entity.iter(f"{EDM}Property")
        }
        for entity in ET.fromstring(metadata).iter(f"{EDM}EntityType")
    }


def bi(en: str, he: str) -> str:
    return f"{en} | {he}"


def expand(col):
    """A column spec is either a COMMON name or (name, source expression, en, he)."""
    if isinstance(col, str):
        return (col, "last_updated_date" if col == "updated_at" else col, *COMMON[col])
    return col


def cast(
    types: dict[str, dict[str, str]], model: str, table: str, name: str, src: str
) -> tuple[str, str]:
    """SQL expression and type for one renamed column."""
    if src.startswith("{{ local_time("):
        return src, "TIMESTAMP"  # Israel local time
    if match := re.fullmatch(r"trim\((\w+)\)", src):
        return f"TRIM({match[1]})", "VARCHAR"
    if match := re.fullmatch(r"NULLIF\((\w+), -1\)", src):  # the source's "none" code
        return src, types[table][match[1]]
    if src.startswith("_dlt_valid"):
        return src, "TIMESTAMPTZ"
    column = src.strip('"')
    return src, TYPE_OVERRIDES.get((model, name)) or types[table][column]


def select_list(lines: list[tuple[str, str, str]]) -> str:
    casts = [f"CAST({expr} AS {sql_type})" for expr, sql_type, _ in lines]
    width = max(len(c) for c in casts)
    return ",\n".join(
        f"        {c:<{width}} AS {name}" for c, (_, _, name) in zip(casts, lines, strict=True)
    )


def generate(types: dict[str, dict[str, str]]) -> tuple[list[dict], list[dict]]:
    """Write one .sql per model; return the source and model YAML entries."""
    sources, models = [], []
    for model, (table, en, he, grain, cols) in MODELS.items():
        scd2 = table not in REPLACED
        cols = [expand(c) for c in cols] + (SCD2_COLUMNS if scd2 else [])
        renamed = [(*cast(types, model, table, name, src), name) for name, src, _, _ in cols]
        key = cols[0][0]
        enhanced = ENHANCED.get(model, [])

        filter_ = (
            f"    WHERE {{{{ is_current('{table}', '{key}') }}}}"
            if scd2
            else "    -- fully replaced on every load: every row is current"
        )
        enhance = (
            (",\n" + select_list([(e, t, n) for n, e, t, _, _ in enhanced])) if enhanced else ""
        )
        sql = f"""-- {en} | {he}
-- Grain: {grain}

WITH source AS (
    SELECT *
    FROM {{{{ source('odata', '{table}') }}}}
),

renamed AS (
    SELECT
{select_list(renamed)}
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
{filter_}
),

enhanced AS (
    SELECT
        *{enhance}
    FROM filtered
)

SELECT *{" EXCLUDE (valid_to)" if scd2 else ""}
FROM enhanced
"""
        (OUT / f"stg_odata__{model}.sql").write_text(sql)

        sources.append({"name": table, "description": bi(en, he)})
        columns = []
        for name, _, c_en, c_he in cols + [(n, e, c_en, c_he) for n, e, _, c_en, c_he in enhanced]:
            if name == "valid_to":
                continue
            column = {"name": name, "description": bi(c_en, c_he)}
            if name == key:
                column["data_tests"] = ["unique", "not_null"]
            columns.append(column)
        models.append(
            {
                "name": f"stg_odata__{model}",
                "description": bi(f"{en}. Grain: {grain}", he),
                "columns": columns,
            }
        )

    # Tests on decoded codes: every code must have a label.
    for m in models:
        for c in m["columns"]:
            if c["name"] in {"gender", "origin"}:
                c["data_tests"] = ["not_null"]
            if c["name"] == "result":
                c["data_tests"] = [
                    {
                        "accepted_values": {
                            "arguments": {
                                "values": ["for", "against", "abstain", "absent", "voted"]
                            }
                        }
                    }
                ]
    return sources, models


def dump(data, path):
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the dbt staging models for OData.")
    parser.add_argument("--metadata", type=Path, help="saved $metadata XML; default: fetch it")
    args = parser.parse_args()
    if args.metadata:
        metadata = args.metadata.read_bytes()
    else:
        from ingestion.odata import Api, load_settings

        metadata = Api(load_settings()).metadata()
    sources, models = generate(source_types(metadata))
    dump(
        {
            "version": 2,
            "sources": [
                {
                    "name": "odata",
                    "description": bi(
                        "Knesset OData v4 tables loaded by ingestion/. Every version of every row is kept (SCD2): "
                        "_dlt_valid_from / _dlt_valid_to, current version has _dlt_valid_to null",
                        "טבלאות OData של הכנסת. כל גרסה של כל שורה נשמרת; לגרסה הנוכחית אין _dlt_valid_to",
                    ),
                    "database": "raw",
                    "schema": "bronze",
                    "tables": sources
                    + [
                        {
                            "name": "deleted_ids",
                            "description": bi(
                                "Rows still in bronze but deleted in the API, found by the weekly check",
                                "שורות שנמחקו ב-API, לפי הבדיקה השבועית",
                            ),
                        }
                    ],
                }
            ],
        },
        OUT / "_odata__sources.yml",
    )
    dump({"version": 2, "models": models}, OUT / "_odata__models.yml")
    print(f"{len(models)} models, {sum(len(m['columns']) for m in models)} columns")


if __name__ == "__main__":
    main()
