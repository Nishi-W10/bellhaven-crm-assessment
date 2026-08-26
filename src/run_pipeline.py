import subprocess
import sys


STEPS = [
    "src/scraper.py",
    "src/crm_client.py",
    "src/matcher.py",
    "src/generate_proposals.py",
]


def run_step(script):
    print("\n" + "=" * 70)
    print(f"RUNNING: {script}")
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, script],
        check=True,
    )

    return result.returncode


def main():
    print("Bellhaven Daily Reconciliation Pipeline")
    print("No CRM writes are performed by this job.")

    for step in STEPS:
        run_step(step)

    print("\nDaily reconciliation completed.")
    print("Open the Streamlit review app to review any new proposals.")


if __name__ == "__main__":
    main()