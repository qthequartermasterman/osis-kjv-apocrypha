from typing import Final
import asyncio

import pyosis
import random
import pathlib
import httpx
from bs4 import BeautifulSoup
import datetime

OUTPUT_DIR = pathlib.Path("osis-documents")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BOOK_NAMES_TO_OSIS_ID = {
    "1 Esdras": "1Esd",
    "2 Esdras": "2Esd",
    "1 Maccabees": "1Macc",
    "2 Maccabees": "2Macc",
    "3 Maccabees": "3Macc",
    "4 Maccabees": "4Macc",
    "Letter of Jeremiah": "EpJer",
    "Prayer of Azariah": "PrAzar",
    "Baruch": "Bar",
    "Prayer of Manasseh": "PrMan",
    "Bel and the Dragon": "Bel",
    "Ecclesiasticus (Wisdom of Sirach)": "Sir",
    "Wisdom of Solomon": "Wis",
    "Additions to Esther": "AddEsth",
    "Tobit": "Tob",
    "Judith": "Jdt",
    "Susanna": "Sus",
    "Psalm 151": "AddPs",
}

BOOK_NAMES_TO_URL = {
    "1 Esdras": "https://www.pseudepigrapha.com/apocrypha_ot/1esdr.htm",
    "2 Esdras": "https://www.pseudepigrapha.com/apocrypha_ot/1macc.htm",
    "1 Maccabees": "https://www.pseudepigrapha.com/apocrypha_ot/1macc.htm",
    "2 Maccabees": "https://www.pseudepigrapha.com/apocrypha_ot/2macc.htm",
    "3 Maccabees": "https://www.pseudepigrapha.com/apocrypha_ot/3macc.htm",
    "4 Maccabees": "https://www.pseudepigrapha.com/apocrypha_ot/4macc.htm",
    "Letter of Jeremiah": "https://www.pseudepigrapha.com/apocrypha_ot/letojer.htm",
    "Prayer of Azariah": "https://www.pseudepigrapha.com/apocrypha_ot/azariah.htm",
    "Baruch": "https://www.pseudepigrapha.com/apocrypha_ot/baruc.htm",
    "Prayer of Manasseh": "https://www.pseudepigrapha.com/apocrypha_ot/manas.htm",
    "Bel and the Dragon": "https://www.pseudepigrapha.com/apocrypha_ot/beldrag.htm",
    "Ecclesiasticus (Wisdom of Sirach)": "https://www.pseudepigrapha.com/apocrypha_ot/sirac.htm",
    "Wisdom of Solomon": "https://www.pseudepigrapha.com/apocrypha_ot/wisolom.htm",
    "Additions to Esther": "https://www.pseudepigrapha.com/apocrypha_ot/esther.htm",
    "Tobit": "https://www.pseudepigrapha.com/apocrypha_ot/tobit.htm",
    "Judith": "https://www.pseudepigrapha.com/apocrypha_ot/judith.htm",
    "Susanna": "https://www.pseudepigrapha.com/apocrypha_ot/susan1.htm",
    "Psalm 151": "https://www.pseudepigrapha.com/apocrypha_ot/Pslm151.htm"
}


async def scrape_book(client:httpx.AsyncClient, book_name: str, book_osis_id: str) -> pyosis.DivCt:
    book_uri = BOOK_NAMES_TO_URL[book_name]
    print(book_name, book_osis_id, book_uri)
    chapters: list[pyosis.ChapterCt] = []

    html = (await client.get(book_uri)).text
    soup = BeautifulSoup(html, "html.parser")

    for p in soup.find_all(["p"]):
        p.unwrap()

    chapters: list[pyosis.ChapterCt] = []
    current_chapter: pyosis.ChapterCt | None = None
    current_verse: pyosis.VerseCt | None = None
    verse_text_parts = []

    for elem in soup.find_all(["h3", "b"], recursive=True):
        if elem.name == "h3":
            # Start a new chapter
            if current_verse is not None:
                assert current_chapter is not None
                current_chapter.content.append(current_verse)
                current_verse = None
            if current_chapter is not None:
                chapters.append(current_chapter)
                current_chapter = None
            *_, chapter_num = elem.get_text().strip().rsplit(".", maxsplit=1)
            int(chapter_num)
            current_chapter = pyosis.ChapterCt(
                osis_id=[f"{book_osis_id}.{chapter_num}"],
                content=[]
            )
        elif elem.name == "b" and not elem.find_parent("center"):
            if current_chapter is None:
                current_chapter = pyosis.ChapterCt(
                    osis_id=[f"{book_osis_id}.{1}"],
                    content=[]
                )
            if current_verse is not None:
                assert current_chapter is not None
                current_chapter.content.append(current_verse)
                current_verse = None
            # Verse number
            verse_number = elem.get_text(strip=True)
            # The text immediately after the <b> tag until next <br> or <b>
            verse_text_parts = []
            for sibling in elem.next_siblings:
                if sibling.name in ["b", "h3"]:
                    break
                if sibling.name == "br":
                    continue
                text = str(sibling).strip()
                if text:
                    verse_text_parts.append(BeautifulSoup(text, "html.parser").get_text())
            verse_text = " ".join(verse_text_parts).strip()
            verse_text = verse_text.replace("\n", " ").replace("\r","").lstrip("]").rstrip("[").strip()
            current_verse = pyosis.VerseCt(
                osis_id=[f"{current_chapter.osis_id[0]}.{verse_number}"],
                content=[verse_text],
            )

    if current_verse is not None:
        assert current_chapter is not None
        current_chapter.content.append(current_verse)
        current_verse = None
    if current_chapter is not None:
        chapters.append(current_chapter)
        current_chapter = None

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
    await asyncio.sleep(random.random()*3)
    book = await scrape_book(client, book_name, book_osis_id)
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
                                        f"Scraped from www.pseudepigrapha.com/apocrypha_ot, and converted to OSIS by the"
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
    async with httpx.AsyncClient() as client:
        tasks = [
            save_book(client, book_name, osis_id)
            for book_name, osis_id in BOOK_NAMES_TO_OSIS_ID.items()
        ]
        books: list[pyosis.DivCt] = await asyncio.gather(*tasks)
        osis = books_to_osis_xml(books)
        (OUTPUT_DIR / "kjv_apocrypha.xml").write_text(osis.to_xml())


if __name__ == "__main__":
    asyncio.run(main())
