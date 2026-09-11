"""Download the raw data into data/raw.

Food.com Recipes and Interactions (2008-2018 cut) comes from the public
Google Drive folder published with UCSD's data science course materials.
NHANES 2017-2018 comes straight from the CDC.

    .venv/Scripts/python src/download_data.py
"""

import urllib.request
from pathlib import Path

import gdown

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

FOOD_COM = {
    "RAW_recipes.csv": "177uOJ7yJyKDNJd3GCfVBbpGE-BzNv0S8",
    "RAW_interactions.csv": "1d4jl5ABzB-Y3PROJg3d6YExS4zaeMOBi",
}
NHANES_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/{}.xpt"
NHANES_FILES = ["DEMO_J", "BMX_J", "DR1TOT_J", "DR2TOT_J", "PAQ_J"]

# Parsed Food.com scrape with photo URLs and original recipe names (photos.py).
PARSED_URL = (
    "https://huggingface.co/datasets/Karo8870/food.com-parsed-dataset/resolve/"
    "refs%2Fconvert%2Fparquet/default/train/{:04d}.parquet"
)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, file_id in FOOD_COM.items():
        path = RAW / name
        if not path.exists():
            print(f"downloading {name}")
            gdown.download(id=file_id, output=str(path), quiet=True)
    for i in range(2):
        path = RAW / f"foodcom_parsed_{i:04d}.parquet"
        if not path.exists():
            print(f"downloading {path.name}")
            urllib.request.urlretrieve(PARSED_URL.format(i), path)
    for name in NHANES_FILES:
        path = RAW / f"{name}.xpt"
        if not path.exists():
            print(f"downloading {name}.xpt")
            urllib.request.urlretrieve(NHANES_URL.format(name), path)
    print("data/raw is complete")


if __name__ == "__main__":
    main()
