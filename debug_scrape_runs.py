import asyncio
from datetime import datetime


async def test():
    from database import repository
    await repository.init_schema()
    # Get source status
    stats = await repository.get_stats()
    print("Source status:")
    for s in stats["source_status"]:
        print(
            f"  {s['source']}: status={s['status']}, "
            f"attempt_status={s['attempt_status']}, "
            f"tenders_found={s['tenders_found']}, "
            f"error={s['error']}"
        )
    print()
    print("Last scan:", stats.get("last_scan"))
    print()
    print("Total tenders:", stats["total_tenders"])
    print("Strong fit count:", stats["strong_fit_count"])
    print("Potential fit count:", stats["potential_fit_count"])


asyncio.run(test())