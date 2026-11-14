-- Approved Gate B rules. source_lines is loaded verbatim apart from text/date serialization.
CREATE TABLE positive_lines AS
SELECT * FROM source_lines
WHERE SUBSTR(invoice, 1, 1) <> 'C' AND quantity > 0 AND unit_price > 0;

CREATE TABLE merchandise_lines AS
SELECT invoice,
       CASE stock WHEN '47566b' THEN '47566B'
                  WHEN '15056n' THEN '15056N'
                  ELSE stock END AS product,
       description, invoice_date, customer_id
FROM positive_lines
WHERE UPPER(stock) NOT IN ('POST','DOT','M','C2','AMAZONFEE','S','B');
CREATE INDEX merchandise_invoice ON merchandise_lines(invoice);

CREATE TABLE invoice_products AS
SELECT DISTINCT invoice, product FROM merchandise_lines;
CREATE UNIQUE INDEX invoice_product_key ON invoice_products(invoice, product);

-- Check the full source invoice time span, including lines removed from the model.
CREATE TABLE invoice_times AS
SELECT s.invoice, MIN(s.invoice_date) AS first_time, MAX(s.invoice_date) AS last_time,
       MAX(s.customer_id) AS customer_id
FROM source_lines s
JOIN (SELECT DISTINCT invoice FROM merchandise_lines) m USING (invoice)
GROUP BY s.invoice;
CREATE UNIQUE INDEX invoice_times_key ON invoice_times(invoice);

CREATE TABLE basket_sizes AS
SELECT invoice, COUNT(*) AS basket_size FROM invoice_products GROUP BY invoice;
CREATE UNIQUE INDEX basket_sizes_key ON basket_sizes(invoice);

-- A whole invoice is eligible only if both ends of its source time span are
-- in the same approved split and its distinct-product size is 2..99.
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
WHERE basket_size >= 2 AND basket_size < 100
  AND first_split IS NOT NULL AND first_split = last_split;
CREATE UNIQUE INDEX split_baskets_key ON split_baskets(invoice);
CREATE INDEX split_baskets_split ON split_baskets(split);

CREATE TABLE basket_items AS
SELECT b.invoice, b.split, p.product
FROM split_baskets b JOIN invoice_products p USING (invoice);
CREATE UNIQUE INDEX basket_items_key ON basket_items(invoice, product);
CREATE INDEX basket_items_split_product ON basket_items(split, product);
