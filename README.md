# Basket Completion

Basket Completion compares product suggestions based on historical co-purchases with a simple popularity baseline. It uses the public UCI Online Retail dataset and includes an offline evaluation and a local Streamlit demo. The demo reads the frozen training catalog and saved results; it does not retrain the model.

On 3,205 later test orders, the co-purchase method recovered a hidden product among its top five suggestions in **18.38%** of cases, compared with **2.00%** for popular products. The app displays the saved results, including uncertainty, coverage, and the larger-order sensitivity.

## Data and scope

The source is Chen, D. (2015). *Online Retail* [Dataset]. UCI Machine Learning Repository. [Dataset page](https://archive.ics.uci.edu/dataset/352/online-retail) · [DOI](https://doi.org/10.24432/C5BW33) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The project cleans and transforms the original transaction lines into product sets for each order.

The primary study uses orders with 2–99 distinct eligible products. Catalog names, product popularity, and co-purchase evidence come only from training orders. Validation selected a fixed method: at least three shared training orders, directional confidence, and the strongest qualifying cart-product relationship. Popular products fill remaining suggestion slots. For evaluation, one product is hidden from each eligible later order and counted as a hit if it appears in the top five suggestions. The [evaluation policy](docs/EVALUATION_SPEC.md) and [frozen file hashes](docs/frozen_config.json) document the rules.

## Setup

Use Python 3.11 or newer. Download `Online Retail.xlsx` from the [dataset page](https://archive.ics.uci.edu/dataset/352/online-retail) and save it as `data/raw/Online Retail.xlsx`.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[demo]'
python -m basket_completion.prepare
python -m basket_completion.validation
python -m basket_completion.export_demo
python -m unittest discover -s tests -q
python -m streamlit run app/main.py
```

Preparation and validation rebuild the ignored SQLite databases from the source workbook. The export command verifies the frozen hashes and writes a compact training-only database and manifest to `data/deploy/`. Commit those two files for Streamlit Community Cloud. The app reads those artifacts and the saved aggregate reports; it does not need the workbook or processed databases at startup. Set the Streamlit entrypoint to `app/main.py`. `requirements.txt` supplies cloud dependencies. To regenerate figures, install the optional `figures` extra and run `python reports/figures/build_final_charts.py`.

## Demo

**Reports and outcomes** opens first and displays the saved evaluation. Select **Demo** to search the full training catalog, add products to a cart, adjust quantities, and inspect suggestions. The Demo shows three ranked items initially; **Show more** reveals the rest of the evaluated top five. Each co-purchase suggestion identifies its supporting cart product and shared training-order count. Popularity-filled suggestions are labeled. Quantities do not affect ranking, and the URL preserves a valid cart across refreshes.

## Limitations

This is offline reconstruction of gift-retail orders, not a measurement of sales impact or product compatibility. Co-purchases can reflect substitutes or similar variants. Products absent from the training catalog cannot be recovered, and the later test period differs seasonally from training. The raw workbook and processed databases remain excluded from Git; the deployment database contains only catalog counts and qualifying aggregate pair evidence.
