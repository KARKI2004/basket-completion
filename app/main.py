"""Streamlit view over frozen training recommendations and saved results."""
from __future__ import annotations
import json
import html
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import streamlit as st
from basket_completion.demo import DemoService, add_product, basket_for_url, basket_from_url, load_saved_results, remove_product, set_quantity
from basket_completion.prepare import ROOT
st.set_page_config(page_title="Basket Completion", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container {max-width:1160px;padding-top:.7rem;padding-bottom:1.3rem;overflow-x:clip}
h1 {font-size:1.65rem!important;line-height:1.3!important;margin:0 0 .15rem!important;overflow:visible}
h2,h3 {letter-spacing:-.015em}
.st-key-browse_panel,.st-key-cart_panel,.st-key-suggestions_panel,
.st-key-report_background,.st-key-report_data,.st-key-report_outcomes,.st-key-report_limits {
  min-width:0;background:#161B22;border:1px solid #374151;border-radius:.5rem;
  padding:.4rem .7rem .55rem;margin:.4rem 0 .65rem;
}
.st-key-browse_panel {border-top:3px solid #83A8C7}
.st-key-cart_panel {border-top:3px solid #82AAA1}
.st-key-suggestions_panel {border-top:3px solid #C1AA7A}
.st-key-report_background,.st-key-report_data,.st-key-report_outcomes,.st-key-report_limits {max-width:900px}
.st-key-report_background {border-top:3px solid #83A8C7}
.st-key-report_data {border-top:3px solid #82AAA1}
.st-key-report_outcomes {border-top:3px solid #C1AA7A}
.st-key-report_limits {border-top:3px solid #83A8C7}
.st-key-browse_panel h3,.st-key-cart_panel h3,.st-key-suggestions_panel h3,
.st-key-report_background h3,.st-key-report_data h3,.st-key-report_outcomes h3,.st-key-report_limits h3 {margin-top:0!important}
.st-key-report_outcomes [data-testid="stMetricValue"] {font-size:1.7rem}
.st-key-report_data p,.st-key-report_background p,.st-key-report_outcomes p,.st-key-report_limits p {max-width:75ch}
.st-key-browse_strip {overflow-x:auto;max-width:100%;padding-bottom:.25rem;scrollbar-color:#83A8C7 #161B22;scrollbar-width:thin}
.st-key-browse_strip [data-testid="stHorizontalBlock"] {flex-wrap:nowrap;min-width:1200px;align-items:stretch}
.st-key-browse_strip [data-testid="column"] {min-width:180px}
.st-key-browse_strip p,.st-key-browse_strip [data-testid="stExpander"] p {overflow-wrap:anywhere}
.product-tile-name {font-weight:600;min-height:3.6rem;line-height:1.3;overflow-wrap:anywhere}
.st-key-browse_strip [data-testid="stVerticalBlockBorderWrapper"],
.st-key-suggestions_panel [data-testid="stVerticalBlockBorderWrapper"] {background:#161B22;border-color:#374151}
.stApp [data-testid="stCaptionContainer"] {color:#B8C0CC}
.stApp button:not(:disabled):hover {border-color:#83A8C7}
.stApp button:disabled {opacity:1;color:#B8C0CC;border-color:#374151;background:#161B22}
.stApp [data-testid="stSegmentedControl"] button[aria-pressed="true"] {background:#83A8C7;color:#0E1117;border-color:#83A8C7}
.stApp :is(button,input,[role="radio"]):focus-visible {outline:3px solid #83A8C7!important;outline-offset:2px}
@media(max-width:640px){
  .block-container{padding:.6rem .65rem 1rem}
  .st-key-browse_strip [data-testid="stHorizontalBlock"]{min-width:560px}
  .st-key-browse_strip [data-testid="column"]{min-width:135px}
  .st-key-browse_panel,.st-key-cart_panel,.st-key-suggestions_panel,
  .st-key-report_background,.st-key-report_data,.st-key-report_outcomes,.st-key-report_limits{padding:.35rem .5rem .5rem}
}
</style>""",unsafe_allow_html=True)

@st.cache_resource(show_spinner="Checking frozen training artifacts…")
def service() -> DemoService:
    return DemoService.from_frozen()


def pct(value: float) -> str:
    return f"{value:.2%}"


def display_name(name: str) -> str:
    return name.strip().lower().capitalize()


def sync_cart_url(cart: dict[str, int]) -> None:
    if cart:
        saved = basket_for_url(cart)
        if st.query_params.get("basket") != saved:
            st.query_params["basket"] = saved
    elif "basket" in st.query_params:
        del st.query_params["basket"]


def add_to_cart(cart: dict[str, int], code: str, known: set[str]) -> None:
    if add_product(cart, code, known) == "duplicate":
        st.session_state["cart_notice"] = "Already in your cart. Adjust its quantity below."
    sync_cart_url(cart)


def remove_from_cart(cart: dict[str, int], code: str) -> None:
    remove_product(cart, code)
    st.session_state.pop(f"qty:{code}", None)
    sync_cart_url(cart)


def clear_cart(cart: dict[str, int]) -> None:
    for code in tuple(cart):
        st.session_state.pop(f"qty:{code}", None)
    cart.clear()
    sync_cart_url(cart)


def change_page(page: int) -> None:
    st.session_state["browse_page"] = page


def set_suggestion_expansion(expanded: bool) -> None:
    st.session_state["show_more_suggestions"] = expanded


def render_demo(model: DemoService) -> None:
    catalog = model.names
    known = set(catalog)
    if "basket" not in st.session_state:
        st.session_state["basket"] = basket_from_url(
            st.query_params.get("basket", ""), known
        )
    cart: dict[str, int] = st.session_state["basket"]

    st.write("Add a product below, then see what goes with your cart.")
    with st.container(key="browse_panel"):
        st.subheader("Browse products")
        query = st.text_input("Search products", placeholder="Name or stock code")
        if query != st.session_state.get("browse_last_query"):
            st.session_state["browse_last_query"] = query
            st.session_state["browse_page"] = 0

        products, total, page = model.browse(
            query, st.session_state.get("browse_page", 0), page_size=8
        )
        st.session_state["browse_page"] = page
        if not products:
            st.info("No matching products in the training catalog.")
        else:
            previous, position, next_page = st.columns([1, 3, 1])
            previous.button(
                "← Previous", disabled=page == 0,
                on_click=change_page, args=(page - 1,),
            )
            position.caption(
                f"Products {page * 8 + 1}–{page * 8 + len(products)} of {total:,} "
                "· scroll sideways or use arrows"
            )
            next_page.button(
                "Next →", disabled=(page + 1) * 8 >= total,
                on_click=change_page, args=(page + 1,),
            )
            with st.container(key="browse_strip"):
                for row in range(2):
                    columns = st.columns(4, gap="small")
                    for column, product in zip(
                        columns, products[row * 4:(row + 1) * 4]
                    ):
                        with column, st.container(border=True):
                            st.markdown(
                                '<div class="product-tile-name">'
                                f"{html.escape(display_name(product.name))}</div>",
                                unsafe_allow_html=True,
                            )
                            st.button(
                                "Add to cart", key=f"browse_add:{product.code}",
                                width="stretch", on_click=add_to_cart,
                                args=(cart, product.code, known),
                            )
                            with st.expander("Details"):
                                st.write(display_name(product.name))
                                st.caption(
                                    f"Stock code: {product.code} · "
                                    f"{product.training_baskets:,} training orders"
                                )
        notice = st.session_state.pop("cart_notice", None)
        if notice:
            st.info(notice)

    cart_col, suggestions_col = st.columns(2, gap="medium")
    with cart_col, st.container(key="cart_panel"):
        st.subheader("Your cart")
        if not cart:
            st.caption("Your cart is empty.")
        else:
            for code in tuple(cart):
                st.markdown(f"**{display_name(catalog.get(code, code))}**")
                quantity_col, remove_col = st.columns([2, 1])
                quantity = quantity_col.number_input(
                    "Qty", min_value=1, max_value=9999, step=1,
                    value=cart[code], key=f"qty:{code}",
                )
                before = cart[code]
                set_quantity(cart, code, int(quantity))
                if cart[code] != before:
                    sync_cart_url(cart)
                remove_col.button(
                    "Remove", key=f"remove:{code}",
                    on_click=remove_from_cart, args=(cart, code),
                )
            st.caption("Quantities don’t affect suggestions")
        st.button(
            "Clear cart", disabled=not cart, type="tertiary",
            on_click=clear_cart, args=(cart,),
        )

    with suggestions_col, st.container(key="suggestions_panel"):
        st.subheader("Suggested items")
        if not cart:
            st.write("Add a product to see suggestions.")
            return

        result = model.recommend(tuple(cart))
        membership = tuple(sorted(cart))
        if st.session_state.get("suggestion_membership") != membership:
            st.session_state["suggestion_membership"] = membership
            st.session_state["show_more_suggestions"] = False

        ranked = result.combined
        shown = ranked if st.session_state["show_more_suggestions"] else ranked[:3]
        if not ranked:
            st.caption("No eligible additions are available.")
        elif len(ranked) > 3:
            st.caption(
                f"Showing {len(shown)} of {len(ranked)} ranked items. "
                "I evaluated five suggestions; this is only a display limit."
            )

        supports = model.supporting_evidence(
            tuple(cart),
            tuple(item.product for item in shown if item.source == "association"),
        )
        for suggestion in shown:
            with st.container(border=True):
                name = display_name(catalog.get(suggestion.product, suggestion.product))
                st.markdown(f"**{name}**")
                if suggestion.source == "association" and suggestion.evidence is not None:
                    evidence = suggestion.evidence
                    antecedent = display_name(
                        catalog.get(evidence.antecedent, evidence.antecedent)
                    )
                    st.caption(
                        f"Bought in {evidence.pair_count} training orders with {antecedent}"
                    )
                    with st.expander("Co-purchase details"):
                        st.caption(
                            "Each count is distinct training orders containing both products. "
                            "Confidence is the share of training orders with the cart product "
                            "that also contained this item. Lift divides that share by the "
                            "item’s overall share of training orders. These historical "
                            "frequencies do not establish compatibility or forecast future purchases."
                        )
                        for row in supports.get(suggestion.product, ()):
                            source_name = display_name(
                                catalog.get(row.antecedent, row.antecedent)
                            )
                            st.write(
                                f"{source_name}: {row.pair_count} shared orders · "
                                f"confidence {row.confidence:.1%} · lift {row.lift:.2f}×"
                            )
                else:
                    st.caption(
                        "Popular overall · popularity fallback; "
                        "no qualifying association selected for this slot"
                    )
                st.button(
                    "Add to cart", key=f"suggest:{suggestion.product}",
                    on_click=add_to_cart, args=(cart, suggestion.product, known),
                )

        if len(ranked) > 3:
            if st.session_state["show_more_suggestions"]:
                st.button(
                    "Show fewer", on_click=set_suggestion_expansion, args=(False,)
                )
            else:
                st.button(
                    f"Show more ({len(ranked) - 3})",
                    on_click=set_suggestion_expansion, args=(True,),
                )
        if len(ranked) < 5:
            st.caption(f"{len(ranked)} eligible additions available.")


def open_demo() -> None:
    st.session_state["view"] = "Demo"
    st.query_params["view"] = "Demo"


def render_results() -> None:
    metrics = load_saved_results()
    primary = metrics["primary"]
    preparation = json.loads((ROOT / "reports/preparation_summary.json").read_text(encoding="utf-8"))
    validation = json.loads((ROOT / "reports/validation_metrics.json").read_text(encoding="utf-8"))
    frozen = json.loads((ROOT / "docs/frozen_config.json").read_text(encoding="utf-8"))
    n = primary["invoices"]
    association_rate = pct(primary["combined_hit_rate_at_5"])
    popularity_rate = pct(primary["baseline_hit_rate_at_5"])
    difference = 100 * primary["difference_from_popularity"]

    with st.container(key="report_background"):
        st.subheader("Project background")
        st.write("When a shopper adds products to a cart, which additional items are worth suggesting? "
                 "I explored cart-based suggestions using historical co-purchases and compared them with recommending popular products.")
        st.write("I conducted this independent case study using public gift-retail transactions.")
        st.button("Try the demo →", type="tertiary", on_click=open_demo)

    with st.container(key="report_data"):
        st.subheader("Data and methodology")
        st.write("I used market basket analysis to learn co-purchase patterns from earlier orders and tested whether they recovered hidden products in later orders.")
        st.markdown("**Data source and scope.** I used the [UCI Online Retail dataset](https://archive.ics.uci.edu/dataset/352/online-retail), containing transactions from a UK-based online retailer selling mainly gifts between 1 December 2010 and 9 December 2011. I focused the primary study on orders with 2–99 distinct eligible products.")
        st.markdown("**Cleaning and order construction.** I kept positive purchase lines, removed identified non-merchandise codes, "
                    "and counted each stock code once per order. I used product presence rather than quantity to calculate recommendations.")
        st.markdown("**Chronological split.** I trained on earlier orders, selected the setting on validation orders, and evaluated it on later test orders.")
        st.caption("Eligible orders · " + " · ".join(
            f"{label.title()} {preparation['splits'][label]['baskets']:,}"
            for label in ("train", "validation", "test")
        ))
        st.markdown("**Recommendation and baseline.** I required at least three training orders shared by a candidate and a cart product. "
                    "Directional confidence is the share of training orders with that cart product that also contained the candidate. "
                    "For carts with multiple products, I used the strongest qualifying confidence. As a baseline, I counted the eligible training orders containing each product, ranked products by that count with stock code breaking ties, and skipped products already in the cart before taking the top five.")
        st.markdown("**Evaluation.** I hid one product from each eligible later order, used the remaining products as the cart, "
                    "and checked whether the hidden product appeared among five suggestions.")
        with st.expander("Detailed method, dates and reproducibility"):
            st.write("I excluded transaction lines from cancellation-prefixed orders and lines with nonpositive quantity or price, then removed the approved non-merchandise codes. "
                     "I applied only two predeclared stock-code case mappings; I left other case variants distinct. "
                     "I formed each order from distinct invoice–stock-code presence, kept orders with missing customer IDs, and excluded any whole order that crossed a split boundary.")
            st.write("I used 2010-12-01 to before 2011-09-01 for training, 2011-09-01 to before 2011-11-01 for validation, "
                     "and 2011-11-01 to before 2011-12-10 for testing. I included orders with 2–99 distinct products in the primary study "
                     "and used the prespecified 2–199-product sensitivity as a robustness check.")
            st.write(f"I used the frozen {frozen['setting']} setting and generated candidates from the training catalog after excluding cart products. "
                     "I broke equal association scores by training popularity, then stock code, and filled remaining slots with labeled popular products. "
                     "I selected each hidden product with a fixed hash of its invoice ID and kept unseen targets in the denominator as misses.")
            st.write(f"I selected this method from the approved eight settings on validation ({next(item['combined_hits'] for item in validation['settings'] if item['key'] == frozen['setting']):,}/{validation['validation_invoices']:,} combined hits). "
                     "After Gate C acceptance, I froze the setting before the first final test scoring. I later inspected and reviewed the test results without retuning. "
                     "Most files are uncommitted, so Git alone cannot independently prove that time order.")
            st.markdown("Chen, D. (2015). *Online Retail* [Dataset]. UCI Machine Learning Repository. [DOI](https://doi.org/10.24432/C5BW33) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). I cleaned and transformed the source transactions for this study.")
            st.caption("I recorded the approved evaluation specification, frozen hash manifest, saved metrics, and reviewed test report in this repository for reproducibility.")

    with st.container(key="report_outcomes"):
        st.subheader("Outcomes")
        c1, c2, c3 = st.columns(3)
        c1.metric("Co-purchase method · top 5", association_rate)
        c2.metric("Popular products · top 5", popularity_rate)
        c3.metric("Difference · percentage points", f"+{difference:.2f}")
        st.write(f"Across {n:,} eligible later orders, I recovered the hidden item in "
                 f"{primary['combined_hits']:,} carts with association suggestions, versus {primary['baseline_hits']:,} with popularity.")
        st.image(str(ROOT / "reports/figures/method_comparison.png"), width="stretch")
        st.caption("I evaluated five suggestions. Demo shows three of those same ranked results at first, with Show more for the rest.")
        low, high = primary["paired_cluster_bootstrap_95pct_difference"]
        st.caption(f"Uncertainty around the difference: 95% interval, +{100*low:.2f} to +{100*high:.2f} percentage points.")
        with st.expander("How I estimated uncertainty"):
            st.write(f"I used {frozen['bootstrap_resamples']:,} fixed-seed paired customer-cluster bootstrap resamples and reported the 95% percentile interval. I grouped orders with the same known customer ID and treated each order with a missing ID as its own cluster. The interval does not capture uncertainty from the catalog or time period.")
        with st.expander("Results by training-product popularity"):
            catalog_counts = metrics["training_catalog_product_counts"]
            st.write(f"I grouped targets by product frequency in training orders: head was the first {catalog_counts['head']:,} catalog products, "
                     f"middle the next {catalog_counts['middle']:,}, and tail the remaining {catalog_counts['tail']:,}. "
                     "I broke frequency ties by stock code. Unseen targets are absent from the training catalog and count as misses.")
            rows = []
            for label in ("head", "middle", "tail", "unseen"):
                group = primary["groups"][label]
                rows.append({"Target group": label.title(), "Test orders": group["invoices"],
                             "Popularity hits": group["baseline_hits"], "Association hits": group["combined_hits"],
                             "Association rate": pct(group["combined_hits"] / group["invoices"])})
            st.dataframe(rows, hide_index=True, width="stretch")
            st.image(str(ROOT / "reports/figures/popularity_breakdown.png"), width="stretch")
        with st.expander("Catalog reach and popularity fallback"):
            st.write(f"I found the hidden target in the training catalog for {primary['known_targets']:,}/{n:,} orders; "
                     f"{primary['unseen_targets']:,} unseen targets remained misses. "
                     f"I found at least one eligible association candidate for {primary['association_coverage_invoices']:,}/{n:,} orders. "
                     f"I used popularity to fill one or more slots for {primary['any_fallback_invoices']:,} orders, "
                     f"including {primary['full_fallback_invoices']:,} with no association candidates. "
                     "I found no additional hits from the popularity fill in the saved test result.")
            st.image(str(ROOT / "reports/figures/coverage_fallback.png"), width="stretch")

    with st.container(key="report_limits"):
        st.subheader("Assumptions and limitations")
        st.markdown("""- Gift-retail transactions may not transfer to restaurant-supply shopping.
- Recovering a hidden historical purchase does not measure sales impact.
- Co-purchases may include substitutes or similar variants; they do not establish compatibility or usefulness.
- Products absent from the training catalog cannot be recovered by this method.
- The November–early-December test period differs seasonally from training.
- The final December segment is incomplete, and missing customer IDs can hide repeat shoppers.
- The one-hidden-item reconstruction assumes completed orders represent useful cart context.""")


try: model=service()
except Exception as exc:
    st.error("The frozen training artifacts are missing or incompatible. The demo cannot start safely.")
    st.code(str(exc)); st.stop()
st.title("Basket Completion")
views=("Reports and outcomes","Demo")
requested_view=st.query_params.get("view")
if "view" not in st.session_state: st.session_state["view"]=requested_view if requested_view in views else views[0]
view=st.segmented_control("View",views,required=True,label_visibility="collapsed",key="view")
if st.query_params.get("view")!=view: st.query_params["view"]=view
if view=="Demo": render_demo(model)
else:
    try: render_results()
    except Exception as exc:
        st.error("Saved reviewed results are missing or incompatible."); st.code(str(exc))
