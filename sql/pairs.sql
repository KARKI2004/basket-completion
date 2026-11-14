-- Pair evidence comes only from approved primary training baskets (2..99 products).
-- Each basket_items row is a distinct invoice-product presence.
DROP VIEW IF EXISTS train_directional_stats;
DROP TABLE IF EXISTS train_pairs;
CREATE TABLE train_pairs AS
SELECT a.product AS product_a, b.product AS product_b, COUNT(*) AS pair_count
FROM basket_items a INDEXED BY basket_items_split_product
JOIN basket_items b INDEXED BY basket_items_key
  ON a.invoice = b.invoice AND a.product < b.product
WHERE a.split = 'train' AND b.split = 'train'
GROUP BY a.product, b.product;
CREATE UNIQUE INDEX train_pairs_ab ON train_pairs(product_a, product_b);
CREATE INDEX train_pairs_ba ON train_pairs(product_b, product_a);

-- Support and lift use the 11,000 (or rebuilt policy-specific) eligible training baskets.
-- Confidence is directional: P(candidate | antecedent).
CREATE VIEW train_directional_stats AS
SELECT p.product_a AS antecedent, p.product_b AS candidate, p.pair_count,
       1.0 * p.pair_count / (SELECT COUNT(*) FROM split_baskets WHERE split='train') AS support,
       1.0 * p.pair_count / a.basket_count AS confidence,
       1.0 * p.pair_count * (SELECT COUNT(*) FROM split_baskets WHERE split='train') /
           (a.basket_count * b.basket_count) AS lift
FROM train_pairs p
JOIN train_popularity a ON a.product=p.product_a
JOIN train_popularity b ON b.product=p.product_b
UNION ALL
SELECT p.product_b, p.product_a, p.pair_count,
       1.0 * p.pair_count / (SELECT COUNT(*) FROM split_baskets WHERE split='train'),
       1.0 * p.pair_count / b.basket_count,
       1.0 * p.pair_count * (SELECT COUNT(*) FROM split_baskets WHERE split='train') /
           (a.basket_count * b.basket_count)
FROM train_pairs p
JOIN train_popularity a ON a.product=p.product_a
JOIN train_popularity b ON b.product=p.product_b;
