from hireember.titles import propose_title_lists, title_filter


def test_exclude_wins_and_reason_as_written():
    assert title_filter("Sales Engineer", ["engineer"], [" Sales "]) == "title: Sales"


def test_boundaries():
    assert title_filter("Salesforce Developer", [], ["sales"]) is None
    assert title_filter("TS-SCI Engineer", [], ["TS/SCI"]) == "title: TS/SCI"


def test_empty_title_and_lists():
    assert title_filter(None, ["x"], []) == "title: not in target roles"
    assert title_filter(None, [], []) is None
    assert title_filter("A", ["", 3], [None]) is None


def test_propose_dedup_and_non_software():
    include, exclude = propose_title_lists(["Nurse", "nurse"])
    assert include == ["nurse"] and exclude == []
    include, exclude = propose_title_lists(["Software Engineer"])
    assert "developer" in include and "sales" in exclude
