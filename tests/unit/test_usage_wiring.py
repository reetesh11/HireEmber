"""Usage shows in the ticket extras section."""

from hireember import usage
from hireember.database import init_db
from hireember.web import queries


def test_extras_rows_show_dashes_counts_and_zero(isolated_db):
    conn = init_db()
    usage.record(conn, 1, "scoring", "<m>", 1200, 150)
    usage.record(conn, 1, "applying", "x", 0, 0)
    html = queries.ticket_extras_html(conn, 1, True)
    assert "<td>1,200</td><td>150</td><td>1,350</td>" in html
    assert "&lt;m&gt;" in html
    assert "<td>Tailoring</td><td>-</td><td>-</td><td>-</td><td>-</td>" in html
    assert "<td>Applying</td><td>x</td><td>0</td><td>0</td><td>0</td>" in html
