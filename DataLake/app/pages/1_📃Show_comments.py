import streamlit as st
import pandas as pd
import mlflow
import mysql.connector

conn = mysql.connector.connect(
    host="mysql",
    user="root",
    password="admin",
    database="olist",
)

cursor = conn.cursor()


def execute_query(query):
    cursor.execute(query)
    result = cursor.fetchall()
    return result


mlflow.set_tracking_uri("http://minio:9000")

def main():
    product_id_input = st.text_input("ProductID","")
    start_date_default = pd.Timestamp("2016-01-01")
    end_date_default = pd.Timestamp("2018-12-12")

    st.sidebar.header("Filters")
    start_date = st.sidebar.date_input("Start Date", value=start_date_default)
    end_date = st.sidebar.date_input("End Date", value=end_date_default)
    emotion_filter = st.sidebar.selectbox(
        "Emotion Filter", ["Positive", "Negative", "All"], index=2
    )

    if st.button("Show comment"):
        if product_id_input:
            check_query = (
                f"SELECT COUNT(*) FROM products WHERE product_id = '{product_id_input}'"
            )
            cursor.execute(check_query)
            product_count = cursor.fetchone()[0]
            if product_count == 0:
                st.write("ProductID not exist. Please re-enter")
            else:
                category_query = f"SELECT product_category_name_english FROM products JOIN product_category_name_translation ON products.product_category_name=product_category_name_translation.product_category_name WHERE product_id = '{product_id_input}'"
                cursor.execute(category_query)
                category_result = cursor.fetchone()
                if category_result:
                    category = category_result[0]
                    st.write(f"Category: {category}")
                query = f"SELECT order_reviews.review_comment_message, order_reviews.review_score, order_reviews.review_creation_date FROM order_reviews JOIN order_items ON order_reviews.order_id = order_items.order_id WHERE order_items.product_id = '{product_id_input}' ORDER BY order_reviews.review_creation_date DESC"
                result = execute_query(query)
                data = []
                for row in result:
                    if row[0]:
                        if row[1] > 3:
                            data.append([row[0], row[2], "positive"])
                        else:
                            data.append([row[0], row[2], "negative"])
                df = pd.DataFrame(data, columns=["Comment", "Date Create", "Sentiment"])
                filtered_data = df

                if start_date and end_date:
                    filtered_data = filtered_data[
                        (filtered_data["Date Create"] >= start_date)
                        & (filtered_data["Date Create"] <= end_date)
                    ]

                num_positive_comments = filtered_data[
                    filtered_data["Sentiment"] == "positive"
                ].shape[0]
                num_negative_comments = filtered_data[
                    filtered_data["Sentiment"] == "negative"
                ].shape[0]

                if emotion_filter == "Positive":
                    st.write("Num of positive comments:", num_positive_comments)
                    filtered_data = filtered_data[
                        filtered_data["Sentiment"] == emotion_filter.lower()
                    ]
                elif emotion_filter == "Negative":
                    st.write("Num of negative comments:", num_negative_comments)
                    filtered_data = filtered_data[
                        filtered_data["Sentiment"] == emotion_filter.lower()
                    ]
                elif emotion_filter == "All":
                    st.write("Num of positive comments:", num_positive_comments)
                    st.write("Num of negative comments:", num_negative_comments)

                st.dataframe(filtered_data, hide_index=True)
        else:
            st.write("Please enter ProductID")


if __name__ == "__main__":
    main()
