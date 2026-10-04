# -*- coding: utf-8 -*-
# Standalone refinement runner - spawned as a detached process by callapi.py.
# Usage: python run_refinement.py <raw_file_path> <target_dir>

import asyncio
import sys

from transcript_agent import refine_transcript


async def main():
    raw_file = sys.argv[1]
    target_dir = sys.argv[2]
    session_id = sys.argv[3] if len(sys.argv) > 3 else None
    firstname = sys.argv[4] if len(sys.argv) > 4 else None
    date_of_birth = sys.argv[5] if len(sys.argv) > 5 else None
    phone_number = sys.argv[6] if len(sys.argv) > 6 else None
    print(
        f"[run_refinement] Starting: {raw_file} -> {target_dir} "
        f"(session_id={session_id}, caller={firstname}/{date_of_birth}, "
        f"phone={phone_number})"
    )
    result = await refine_transcript(
        raw_file,
        target_dir,
        session_id=session_id,
        firstname=firstname,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    print(f"[run_refinement] Done: {result}")


if __name__ == "__main__":
    asyncio.run(main())
