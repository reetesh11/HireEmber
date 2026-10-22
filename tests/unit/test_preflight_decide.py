from hireember import preflight
from hireember.preflight import Need


def _need(key, stages):
    return Need(key, key, tuple(stages), "fix", True, "detail")


def test_pdf_follows_cover_and_notes_group_by_reason():
    out = preflight._decide("run", ["all"], [_need("quality_tier", ["tailor", "cover"])])
    assert out.stages == ["discover", "enrich", "score"]
    assert preflight.skip_notes(out.skipped) == ["Skipping tailor, cover, pdf: quality model is not set up."]


def test_nothing_left_means_no_proceed():
    out = preflight._decide("run", ["tailor"], [_need("quality_tier", ["tailor"])])
    assert out.proceed is False and out.stages == []
