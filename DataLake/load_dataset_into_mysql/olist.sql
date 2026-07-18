CREATE DATABASE olist;
USE olist;

CREATE TABLE product_category_name_translation (
    product_category_name varchar(64),
    product_category_name_english varchar(64),
    PRIMARY KEY (product_category_name)
);

-- #CREATE TABLE geolocation (
-- #    geolocation_zip_code_prefix INT NOT NULL,
-- #    geolocation_lat FLOAT NOT NULL,
-- #    geolocation_lng FLOAT NOT NULL,
-- #    geolocation_city VARCHAR(64) NOT NULL,
-- #    geolocation_state VARCHAR(64) NOT NULL, 
-- #    PRIMARY KEY (geolocation_zip_code_prefix)
-- #);
CREATE TABLE geolocation (
    geolocation_zip_code_prefix INT,
    geolocation_lat FLOAT ,
    geolocation_lng FLOAT ,
    geolocation_city NVARCHAR(64) ,
    geolocation_state VARCHAR(64)
);

CREATE TABLE sellers (
    seller_id varchar(64)  ,
    seller_zip_code_prefix INT ,
    seller_city varchar(64) ,
    seller_state varchar(64) ,
    PRIMARY KEY (seller_id)
);

CREATE TABLE customers (
    customer_id varchar(64) ,
    customer_unique_id varchar(32) ,
    customer_zip_code_prefix INT,
    customer_city varchar(64) ,
    customer_state varchar(64) ,
	PRIMARY KEY (customer_id)
);

CREATE TABLE products (
    product_id varchar(64) ,
    product_category_name varchar(64) ,
    product_name_length int ,
    product_description_length FLOAT ,
    product_photos_qty int ,
    product_weight_g int ,
    product_length_cm float ,
    product_height_cm float ,
    product_width_cm float ,
    PRIMARY KEY (product_id),
    FOREIGN KEY (product_category_name) REFERENCES product_category_name_translation(product_category_name)
);

CREATE TABLE orders (
    order_id varchar(64) ,
    customer_id varchar(64) ,
    order_status varchar(32) ,
    order_purchase_timestamp date ,
    order_approved_at date ,
    order_delivered_carrier_date date ,
    order_delivered_customer_date date ,
    order_estimated_delivery_date date ,
	PRIMARY KEY (order_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
	order_id varchar(64),
    order_item_id int,
    product_id varchar(64),
    seller_id varchar(64),
    shipping_limit_date date,
    price float,
    freight_value float,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE payments (
    order_id varchar(64) ,
    payment_sequential int ,
    payment_type varchar(32) ,
    payment_installments float ,
    payment_value float ,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE order_reviews (
    review_id varchar(64),
    order_id varchar(64) ,
    review_score int ,
    review_comment_title text,
    review_comment_message text,
    review_creation_date date ,
    review_answer_timestamp date,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- SHOW VARIABLES LIKE 'secure_file_priv'
