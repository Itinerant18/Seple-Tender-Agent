import pytest

from scheduler import run_once


@pytest.mark.asyncio
async def test_schema_failure_closes_pool_and_fails_the_cron_job(monkeypatch):
    pool_closed = False
    cycle_called = False

    async def init_schema():
        return False

    async def run_cycle():
        nonlocal cycle_called
        cycle_called = True
        return {"scan_succeeded": True, "digest_count": 0}

    async def close_pool():
        nonlocal pool_closed
        pool_closed = True

    monkeypatch.setattr(run_once.repository, "init_schema", init_schema)
    monkeypatch.setattr(run_once, "run_cycle", run_cycle)
    monkeypatch.setattr(run_once, "close_pool", close_pool)

    with pytest.raises(RuntimeError, match="schema initialization failed"):
        await run_once.main()

    assert pool_closed is True
    assert cycle_called is False


@pytest.mark.asyncio
async def test_scan_failure_closes_pool_and_fails_the_cron_job(monkeypatch):
    pool_closed = False

    async def init_schema():
        return True

    async def run_cycle():
        return {"scan_succeeded": False, "digest_count": 0}

    async def close_pool():
        nonlocal pool_closed
        pool_closed = True

    monkeypatch.setattr(run_once.repository, "init_schema", init_schema)
    monkeypatch.setattr(run_once, "run_cycle", run_cycle)
    monkeypatch.setattr(run_once, "close_pool", close_pool)

    with pytest.raises(RuntimeError, match="Tender scan failed"):
        await run_once.main()

    assert pool_closed is True
