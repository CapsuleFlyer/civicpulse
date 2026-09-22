"""Persistence-level behaviour: the seed is idempotent, aggregates are correct."""

from sqlalchemy import func, select

from app.models import Complaint
from app.repositories.complaints import ComplaintRepository
from app.seed import SEED_COMPLAINTS, seed


async def _count(session) -> int:
    return int((await session.execute(select(func.count()).select_from(Complaint))).scalar_one())


async def test_seed_is_idempotent(app_factory) -> None:
    app = await app_factory()
    factory = app.state.sessionmaker

    async with factory() as session:
        inserted, skipped = await seed(session)
        assert inserted == len(SEED_COMPLAINTS)
        assert skipped == 0
        assert await _count(session) == len(SEED_COMPLAINTS)

    async with factory() as session:
        inserted, skipped = await seed(session)
        assert inserted == 0
        assert skipped == len(SEED_COMPLAINTS)
        assert await _count(session) == len(SEED_COMPLAINTS)


async def test_seed_spreads_across_categories_and_statuses(app_factory) -> None:
    app = await app_factory()
    async with app.state.sessionmaker() as session:
        await seed(session)
        aggregates = await ComplaintRepository(session).aggregate()

    assert aggregates["total"] == len(SEED_COMPLAINTS)
    populated = [name for name, count in aggregates["by_category"].items() if count]
    assert len(populated) >= 4, "a dashboard demo needs more than one bar"
    assert aggregates["by_status"]["open"] > 0
    assert aggregates["by_status"]["resolved"] > 0


async def test_repository_orders_newest_first(app_factory) -> None:
    app = await app_factory()
    async with app.state.sessionmaker() as session:
        await seed(session)
        rows, total = await ComplaintRepository(session).list_page(page=1, page_size=5)

    assert total == len(SEED_COMPLAINTS)
    timestamps = [row.created_at for row in rows]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_rule_engine_flags_the_dangerous_seed_rows(app_factory) -> None:
    app = await app_factory()
    async with app.state.sessionmaker() as session:
        await seed(session)
        rows, _ = await ComplaintRepository(session).list_page(page=1, page_size=100)

    burst = next(row for row in rows if "Burst water main" in row.text)
    assert burst.category.value == "water"
    assert burst.priority.value == "high"
