"""Recipe photos and original recipe names.

RAW_recipes.csv has no photos, and its names are lower-case with punctuation
stripped ("carina s tofu vegetable kebabs"). The larger Food.com Recipes and
Reviews scrape, in the parsed copy published on Hugging Face as
Karo8870/food.com-parsed-dataset, keeps both. It has no id column, but every
photo URL carries the Food.com recipe id in its path

    https://img.sndimg.com/food/image/upload/<transform>/v1/img/recipes/<id split in folders>/<file>.jpg

and that is the same id RAW_recipes uses, so photos and original names join
exactly. Recipes without a photo have no id to join on and keep their
cleaned-up title.

Photos are served from Food.com's image CDN, not copied into the project.
"""

import html
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from recipes import DATA_DIR, PROCESSED_DIR

PARSED_FILES = ["foodcom_parsed_0000.parquet", "foodcom_parsed_0001.parquet"]
PARSED_URL = (
    "https://huggingface.co/datasets/Karo8870/food.com-parsed-dataset/resolve/"
    "refs%2Fconvert%2Fparquet/default/train/{:04d}.parquet"
)

FIRST_URL = re.compile(r'https://[^"\s\]]+')
# Food.com splits the id into two-digit folders: recipe 284828 lives under
# /img/recipes/28/48/28/, recipe 38 under /img/recipes/38/.
RECIPE_ID = re.compile(r"/img/recipes/((?:\d+/)+)")

# The CDN resizes on request; the scraped URLs ask for a 555x416 fit.
SOURCE_TRANSFORM = "w_555,h_416,c_fit,fl_progressive,q_95"
CARD_TRANSFORM = "w_640,h_420,c_fill,fl_progressive,q_80"


def load_photos(data_dir=DATA_DIR, cache=True):
    """One row per recipe id with its first photo URL and original name."""
    path = PROCESSED_DIR / "photos.parquet"
    if cache and path.exists():
        return pd.read_parquet(path)

    # Plain Python regexes: pandas' Arrow-backed string methods silently
    # matched almost nothing on this column.
    rows = []
    for name in PARSED_FILES:
        table = pq.read_table(Path(data_dir) / name, columns=["name", "images"])
        for title, images in zip(table.column("name").to_pylist(), table.column("images").to_pylist()):
            url = FIRST_URL.search(images or "")
            if not url:
                continue
            recipe_id = RECIPE_ID.search(url.group(0))
            if recipe_id:
                # Names were scraped from HTML and keep entities such as &amp;.
                name_text = html.unescape(title) if title else None
                rows.append((int(recipe_id.group(1).replace("/", "")), url.group(0), name_text))
    photos = pd.DataFrame(rows, columns=["recipe_id", "photo_url", "original_name"])
    photos = photos.drop_duplicates("recipe_id").reset_index(drop=True)

    if cache:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        photos.to_parquet(path, index=False)
    return photos


def card_url(photo_url):
    """The same photo cropped to fill a recipe card."""
    return photo_url.replace(SOURCE_TRANSFORM, CARD_TRANSFORM)


def attach_photos(catalog, photos=None):
    """Add ``photo_url``, ``card_url`` and ``display_name`` to the catalogue."""
    photos = load_photos() if photos is None else photos
    out = catalog.drop(columns=["photo_url", "card_url", "display_name"], errors="ignore")
    out = out.merge(photos, on="recipe_id", how="left")
    out["card_url"] = out["photo_url"].map(card_url, na_action="ignore")
    out["display_name"] = out["original_name"].fillna(out["title"])
    return out.drop(columns=["original_name"])
