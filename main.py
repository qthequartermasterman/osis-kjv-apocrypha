from typing import Final
import asyncio

from playwright.async_api._generated import Browser, Page
import pyosis
import pathlib
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import datetime

KJV_WEBSITE: Final = "https://www.kingjamesbibleonline.org/"
BASE_APOCRYPHA_PAGE: Final = "Apocrypha-Books/"
OUTPUT_DIR = pathlib.Path("osis-documents")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BOOK_NAMES_TO_OSIS_ID = {
    "1 Esdras": "1Esd",
    "2 Esdras": "2Esd",
    "Tobit": "Tob",
    "Judith": "Jdt",
    "Additions to Esther": "AddEsth",
    "Wisdom of Solomon": "Wis",
    "Ecclesiasticus": "Sir",
    "Baruch": "Bar",
    "Letter of Jeremiah": "EpJer",
    "Prayer of Azariah": "PrAzar",
    "Susanna": "Sus",
    "Bel and the Dragon": "Bel",
    "Prayer of Manasseh": "PrMan",
    "1 Maccabees": "1Macc",
    "2 Maccabees": "2Macc",
    # # "3 Maccabees": "3Macc",
    # # "4 Maccabees": "4Macc",
}


def book_name_to_uri_template(book_name: str) -> str:
    return "-".join(book_name.split()) + "-Chapter-{chapter_num}"


async def scrape_chapter(
    page: Page,
    book_uri_template: str,
    chapter_number: int,
    book_osis_id: str,
) -> pyosis.ChapterCt:
    verse_elements: list[pyosis.VerseCt] = []

    url = KJV_WEBSITE + book_uri_template.format(chapter_num=chapter_number)
    print(f"Visiting {url=}")
    response = await page.goto(url)
    if page.url.rstrip("/") != url.rstrip("/"):
        print(f"Expected {url}, but got {response.url}")
        raise ValueError(f"Redirect detected for {url} (actual: {response.url})")
    # Wait for the verses to load
    try:
        await page.wait_for_selector("#div a")
    except Exception as e:
        raise Exception(f"No verse found for {url}. {await page.content()}") from e
    html = await page.content()

    soup = BeautifulSoup(html, "html.parser")
    verse_links = soup.select("#div a")

    for verse_link in verse_links:
        verse_span = verse_link.find("span", class_="versehover")
        verse_number = int(verse_span.text.strip()) if verse_span else None
        if verse_span:
            verse_span.extract()
        verse_text = verse_link.get_text(strip=True)
        verse_elements.append(
            pyosis.VerseCt(
                osis_id=[f"{book_osis_id}.{chapter_number}.{verse_number}"],
                content=[verse_text],
                canonical=True,
            )
        )
    chapter = pyosis.ChapterCt(
        osis_id=[f"{book_osis_id}.{chapter_number}"],
        content=verse_elements,
    )
    print(str(chapter.content)[:140])
    return chapter


async def scrape_book(page: Page, book_name: str, book_osis_id: str) -> pyosis.DivCt:
    book_uri = book_name_to_uri_template(book_name)
    print(book_name, book_osis_id, book_uri)
    chapters: list[pyosis.ChapterCt] = []
    chapter_number = 1
    while True:
        print(f"Trying {book_name} Chapter {chapter_number}")
        try:
            chapter = await scrape_chapter(
                page,
                book_uri_template=book_uri,
                chapter_number=chapter_number,
                book_osis_id=book_osis_id,
            )
            await asyncio.sleep(2)
        except Exception as e:
            # If navigation fails, assume no more chapters
            print(f"Got error. Ending book. {e}")
            break
        else:
            chapters.append(chapter)
            chapter_number += 1

    return pyosis.DivCt(
        osis_id=[book_osis_id],
        type_value=pyosis.OsisDivs.BOOK,
        content=[
            pyosis.HeadCt(content=[book_name]),
            *chapters,
        ],
    )


async def save_book(
    browser: Browser, book_name: str, book_osis_id: str
) -> pyosis.DivCt:
    page: Page = await browser.new_page(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    book = await scrape_book(page, book_name, book_osis_id)
    osis = books_to_osis_xml([book])
    file_name = "_".join(book_name.split()) + ".xml"
    (OUTPUT_DIR / file_name).write_text(osis.to_xml())
    return book


def books_to_osis_xml(books: list[pyosis.DivCt]) -> pyosis.OsisXML:
    return pyosis.OsisXML(
        osis=pyosis.Osis(
            osis_text=pyosis.OsisTextCt(
                header=pyosis.HeaderCt(
                    work=[
                        pyosis.WorkCt(
                            osis_work="King James Version Apocrypha",
                            title=[
                                pyosis.TitleCt(
                                    content=["King James Version--Apocrypha"]
                                )
                            ],
                            type_value=[
                                pyosis.TypeCt(
                                    type_value=pyosis.OsisType.OSIS, value="Bible"
                                )
                            ],
                        )
                    ],
                    revision_desc=[
                        pyosis.RevisionDescCt(
                            date=pyosis.DateCt(
                                event=pyosis.OsisEvents.EVERSION,
                                content=[
                                    datetime.datetime.now().strftime(
                                        "%Y.%m.%dT%H:%M:%S"
                                    )
                                ],
                                lang="en",
                            ),
                            p=[
                                pyosis.PCt(
                                    content=[
                                        "Scraped from https://www.kingjamesbibleonline.org/, and converted to OSIS by the"
                                        " osis-kjv-apocrypha Python package."
                                    ]
                                )
                            ],
                        )
                    ],
                ),
                lang="en",
                div=books,
                osis_idwork="kjv-apocrypha",
            )
        )
    )


async def main() -> None:
    async with Stealth().use_async(async_playwright()) as p:
        browser: Browser = await p.chromium.launch(headless=False)

        tasks = [
            save_book(browser, book_name, osis_id)
            for book_name, osis_id in BOOK_NAMES_TO_OSIS_ID.items()
        ]
        books: list[pyosis.DivCt] = await asyncio.gather(*tasks)
        osis = books_to_osis_xml(books)
        (OUTPUT_DIR / "kjv_apocrypha.xml").write_text(osis.to_xml())
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
