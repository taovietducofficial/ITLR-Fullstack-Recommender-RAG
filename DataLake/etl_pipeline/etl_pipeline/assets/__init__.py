from dagster import load_assets_from_modules

from . import bronze, bronze_itlr, eda, gold, gold_itlr, ml, platinum, silver, silver_itlr

bronze_layer_assets = load_assets_from_modules([bronze])
silver_layer_assets = load_assets_from_modules([silver])
gold_layer_assets = load_assets_from_modules([gold])
platinum_layer_assets = load_assets_from_modules([platinum])
ml_layer_assets = load_assets_from_modules([ml])
eda_layer_assets = load_assets_from_modules([eda])

itlr_bronze_assets = load_assets_from_modules([bronze_itlr])
itlr_silver_assets = load_assets_from_modules([silver_itlr])
itlr_gold_assets = load_assets_from_modules([gold_itlr])
