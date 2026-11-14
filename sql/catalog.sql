-- Each eligible training invoice contributes one vote to product popularity.
CREATE TABLE train_popularity AS
SELECT product, COUNT(*) AS basket_count
FROM basket_items WHERE split = 'train'
GROUP BY product;
CREATE UNIQUE INDEX train_popularity_key ON train_popularity(product);

-- A training invoice/product receives at most one normalized name vote.
CREATE TABLE train_name_votes AS
SELECT m.invoice, m.product, MIN(m.description) AS description
FROM merchandise_lines m
JOIN split_baskets b ON b.invoice = m.invoice AND b.split = 'train'
WHERE m.description IS NOT NULL AND m.description <> ''
GROUP BY m.invoice, m.product;

CREATE TABLE train_catalog AS
WITH name_counts AS (
  SELECT product, description, COUNT(*) AS invoice_votes
  FROM train_name_votes GROUP BY product, description
), ranked AS (
  SELECT product, description,
         ROW_NUMBER() OVER (PARTITION BY product ORDER BY invoice_votes DESC, description ASC) AS name_rank
  FROM name_counts
)
SELECT p.product, COALESCE(r.description, p.product) AS display_name, p.basket_count
FROM train_popularity p LEFT JOIN ranked r ON p.product = r.product AND r.name_rank = 1;
CREATE UNIQUE INDEX train_catalog_key ON train_catalog(product);
