-- Rebuild only eligibility-dependent tables in a copy of the primary database.
-- All cleaning, identity, timestamp, and date rules are unchanged; only the
-- approved distinct-product cap changes from <100 to <200.
DROP VIEW IF EXISTS train_directional_stats;
DROP TABLE IF EXISTS train_pairs;
DROP TABLE IF EXISTS train_catalog;
DROP TABLE IF EXISTS train_name_votes;
DROP TABLE IF EXISTS train_popularity;
DROP TABLE IF EXISTS basket_items;
DROP TABLE IF EXISTS split_baskets;

CREATE TABLE split_baskets AS
WITH classified AS (
  SELECT b.invoice, b.basket_size, t.first_time, t.last_time, t.customer_id,
    CASE WHEN t.first_time >= '2010-12-01 00:00:00' AND t.first_time < '2011-09-01 00:00:00' THEN 'train'
         WHEN t.first_time >= '2011-09-01 00:00:00' AND t.first_time < '2011-11-01 00:00:00' THEN 'validation'
         WHEN t.first_time >= '2011-11-01 00:00:00' AND t.first_time < '2011-12-10 00:00:00' THEN 'test'
    END AS first_split,
    CASE WHEN t.last_time >= '2010-12-01 00:00:00' AND t.last_time < '2011-09-01 00:00:00' THEN 'train'
         WHEN t.last_time >= '2011-09-01 00:00:00' AND t.last_time < '2011-11-01 00:00:00' THEN 'validation'
         WHEN t.last_time >= '2011-11-01 00:00:00' AND t.last_time < '2011-12-10 00:00:00' THEN 'test'
    END AS last_split
  FROM basket_sizes b JOIN invoice_times t USING (invoice)
)
SELECT invoice, basket_size, first_time AS invoice_time, customer_id, first_split AS split
FROM classified
WHERE basket_size >= 2 AND basket_size < 200
  AND first_split IS NOT NULL AND first_split = last_split;
CREATE UNIQUE INDEX split_baskets_key ON split_baskets(invoice);
CREATE INDEX split_baskets_split ON split_baskets(split);

CREATE TABLE basket_items AS
SELECT b.invoice, b.split, p.product
FROM split_baskets b JOIN invoice_products p USING (invoice);
CREATE UNIQUE INDEX basket_items_key ON basket_items(invoice, product);
CREATE INDEX basket_items_split_product ON basket_items(split, product);
