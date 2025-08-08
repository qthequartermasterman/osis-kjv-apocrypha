from typing import Final
import httpx
import bs4
import asyncio
import pyosis
import pathlib


KJV_WEBSITE: Final = "https://www.kingjamesbibleonline.org/"
BASE_APOCRYPHA_PAGE: Final = "Apocrypha-Books/"
OUTPUT_DIR = pathlib.Path("osis-documents")

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
    # "3 Maccabees": "3Macc",
    # "4 Maccabees": "4Macc",
}


# async def get_books(client: httpx.AsyncClient) -> dict[str, str]:
#     response = await client.get(BASE_APOCRYPHA_PAGE)
#     print(response.text)
#     soup = bs4.BeautifulSoup(response.text)

#     links = soup.select(".column a")
#     hrefs = {link.text: str(link["href"]) for link in links}
#     return hrefs


def book_name_to_uri_template(book_name: str) -> str:
    return "-".join(book_name.split()) + "-Chapter-{chapter_num}"


async def scrape_chapter(
    client: httpx.AsyncClient,
    book_uri_template: str,
    chapter_number: int,
    book_name: str,
    book_osis_id: str,
) -> pyosis.ChapterCt:
    verse_elements: list[pyosis.VerseCt] = []

    response = await client.get(book_uri_template.format(chapter_num=chapter_number))
    if response.is_redirect:
        raise httpx.HTTPStatusError(
            "Redirect detected", request=response.request, response=response
        )
    soup = bs4.BeautifulSoup(response.text)
    verse_links = soup.select("#div a")

    # The verse a elements look like:
    # <a href="../1-Esdras-9-1/" title="1 Esdras 9:1 KJV verse detail"><span id="3" class="versehover">1 </span>Then Esdras rising from the court of the temple went to the chamber of Joanan the son of Eliasib,</a>

    for verse_link in verse_links:
        # The verse number is in the <span id="..."> inside the <a>
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

    return pyosis.ChapterCt(
        osis_id=[f"{book_osis_id}.{chapter_number}"],
        content=verse_elements,
    )


async def scrape_book(
    client: httpx.AsyncClient, book_name: str, book_osis_id: str
) -> pyosis.DivCt:
    book_uri = book_name_to_uri_template(book_name)
    print(book_name, book_osis_id, book_uri)
    chapters: list[pyosis.ChapterCt] = []
    chapter_number = 1
    while True:
        try:
            chapter = await scrape_chapter(
                client,
                book_uri_template=book_uri,
                chapter_number=chapter_number,
                book_name=book_name,
                book_osis_id=book_osis_id,
            )
        except httpx.HTTPStatusError as e:
            if "Redirect detected" not in str(e):
                raise e
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
    client: httpx.AsyncClient, book_name: str, book_osis_id: str
) -> pyosis.DivCt:
    book = await scrape_book(client, book_name, book_osis_id)

    osis = books_to_osis_xml([book])

    file_name = "_".join(book_name.split()) + ".xml"

    (OUTPUT_DIR / file_name).write_text(osis.to_xml())
    return book


def books_to_osis_xml(books: list[pyosis.DivCt]) -> pyosis.OsisXML:
    # TODO: put scraping details
    # TODO: put details about the KJV header
    return pyosis.OsisXML(
        osis=pyosis.Osis(
            osis_text=pyosis.OsisTextCt(
                header=pyosis.HeaderCt(
                    work=[
                        pyosis.WorkCt(
                            osis_work="King James Version Apocrypha",
                        )
                    ]
                ),
                div=books,
            )
        )
    )


async def main() -> None:
    async with httpx.AsyncClient(base_url=KJV_WEBSITE) as client:
        tasks = [
            save_book(client, book_name, osis_id)
            for book_name, osis_id in BOOK_NAMES_TO_OSIS_ID.items()
        ]
        books: list[pyosis.DivCt] = await asyncio.gather(*tasks)

        osis = books_to_osis_xml(books)
        (OUTPUT_DIR / "kjv_apocrypha").write_text(osis.to_xml())


if __name__ == "__main__":
    asyncio.run(main())
