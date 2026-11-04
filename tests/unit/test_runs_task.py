import pytest

from hireember import runs


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    yield c
    close_connection(isolated_db)


def test_failure_is_stored_as_last_result(conn):
    def work(c):
        raise RuntimeError("kaboom")

    runs.start_task_async("add-jobs", work, conn=conn).join(10)
    assert not runs.is_running(conn)
    assert "kaboom" in runs.last_stage_result(conn)["message"]


def test_work_runs_on_its_own_connection(conn):
    seen = []
    runs.start_task_async("t", lambda c: seen.append(c is not conn), conn=conn).join(10)
    assert seen == [True]
