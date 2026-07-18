from dagster import load_assets_from_modules

from . import bronze, eda, gold, ml, platinum, silver

bronze_layer_assets = load_assets_from_modules([bronze])
silver_layer_assets = load_assets_from_modules([silver])
gold_layer_assets = load_assets_from_modules([gold])
platinum_layer_assets = load_assets_from_modules([platinum])
ml_layer_assets = load_assets_from_modules([ml])
eda_layer_assets = load_assets_from_modules([eda])
