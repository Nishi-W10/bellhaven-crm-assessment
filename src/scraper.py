import csv
import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://analyst-assessment-production.up.railway.app"
COMMUNITIES_URL = f"{BASE_URL}/communities"
OUTPUT_FILE = "data/raw/website_locations.csv"

EXPECTED_FACILITY_COUNT = 35


def get_page_soup(url):
    """Download a page and return parsed HTML."""
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_directory_facility_urls():
    """Collect community URLs from all directory pages."""
    facility_urls = set()

    for page in range(1, 4):
        if page == 1:
            page_url = COMMUNITIES_URL
        else:
            page_url = f"{COMMUNITIES_URL}?page={page}"

        soup = get_page_soup(page_url)

        page_links = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if "/communities/" in href:
                full_url = urljoin(BASE_URL, href)
                page_links.add(full_url)
                facility_urls.add(full_url)

        print(f"Directory page {page}: {len(page_links)} facilities")

    return facility_urls


def get_homepage_facility_urls():
    """Collect community links promoted on the homepage."""
    soup = get_page_soup(BASE_URL)

    facility_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/communities/" in href:
            facility_urls.add(urljoin(BASE_URL, href))

    return facility_urls


def get_all_facility_urls():
    """Combine directory and homepage facility URLs."""
    directory_urls = get_directory_facility_urls()
    homepage_urls = get_homepage_facility_urls()

    all_urls = directory_urls | homepage_urls

    print()
    print(f"Directory facilities: {len(directory_urls)}")
    print(f"Homepage facility links: {len(homepage_urls)}")
    print(f"Total unique facilities: {len(all_urls)}")
    print()

    if len(all_urls) != EXPECTED_FACILITY_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_FACILITY_COUNT} facilities, "
            f"but found {len(all_urls)}."
        )

    return sorted(all_urls)


def parse_city_state_zip(location_line):
    """Parse 'City, ST 12345' into separate fields."""
    pattern = r"^(.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$"

    match = re.match(pattern, location_line.strip())

    if not match:
        raise ValueError(
            f"Could not parse city/state/zip: {location_line}"
        )

    city, state, zip_code = match.groups()

    return city.strip(), state, zip_code


def scrape_facility(url):
    """Extract facility information from one community page."""
    soup = get_page_soup(url)

    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]

    try:
        address_index = lines.index("Address")
        care_index = lines.index("Care Offerings")
    except ValueError as error:
        raise ValueError(
            f"Expected page labels were not found for {url}"
        ) from error

    # Facility name appears immediately before "Address"
    name = lines[address_index - 1]

    street = lines[address_index + 1]
    location_line = lines[address_index + 2]

    city, state, zip_code = parse_city_state_zip(location_line)

    # Care offerings continue until the next section
    end_markers = [
        "Administrator",
        "Phone",
        "← Back to all communities",
    ]

    care_end = len(lines)

    for marker in end_markers:
        if marker in lines:
            marker_index = lines.index(marker)

            if marker_index > care_index:
                care_end = min(care_end, marker_index)

    care_offerings = lines[care_index + 1:care_end]

    if not care_offerings:
        raise ValueError(
            f"No care offerings found for {name}"
        )

    return {
        "name": name,
        "address": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "care_offerings": " | ".join(care_offerings),
        "source_url": url,
    }


def save_to_csv(facilities):
    """Save scraped facilities to CSV."""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    fieldnames = [
        "name",
        "address",
        "city",
        "state",
        "zip",
        "care_offerings",
        "source_url",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(facilities)


def validate_facilities(facilities):
    """Perform basic data-quality checks."""

    if len(facilities) != EXPECTED_FACILITY_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_FACILITY_COUNT} records, "
            f"but scraped {len(facilities)}."
        )

    required_fields = [
        "name",
        "address",
        "city",
        "state",
        "zip",
        "care_offerings",
        "source_url",
    ]

    for facility in facilities:
        for field in required_fields:
            if not facility[field]:
                raise ValueError(
                    f"Missing {field} for facility: {facility}"
                )

    urls = [facility["source_url"] for facility in facilities]

    if len(urls) != len(set(urls)):
        raise ValueError("Duplicate facility URLs detected.")

    print()
    print("VALIDATION PASSED")
    print(f"Facility records: {len(facilities)}")
    print("Missing required values: 0")
    print("Duplicate URLs: 0")


def main():
    facility_urls = get_all_facility_urls()

    facilities = []

    print("Scraping facility details...")
    print("-" * 70)

    for number, url in enumerate(facility_urls, start=1):

        facility = scrape_facility(url)
        facilities.append(facility)

        print(
            f"{number:02}. "
            f"{facility['name']} | "
            f"{facility['city']}, {facility['state']} | "
            f"{facility['care_offerings']}"
        )

    validate_facilities(facilities)

    save_to_csv(facilities)

    print()
    print(f"Saved: {OUTPUT_FILE}")
    print("Website scraping complete.")


if __name__ == "__main__":
    main()