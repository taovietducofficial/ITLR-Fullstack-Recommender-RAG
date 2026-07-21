"""Mở rộng từ điển khái niệm CNTT (offline). Thêm các khái niệm THẬT còn thiếu mà catalog hay
nhắc tới (data/ML). Bỏ qua key đã có; lọc `related` về key tồn tại; lưu backup trước khi ghi.

Chạy:  python scripts/expand_glossary.py
"""
import json
import shutil
from pathlib import Path

GLOSSARY = Path(__file__).resolve().parent.parent / "itlr" / "chatbot" / "data" / "it_glossary.json"

NEW = {
    "data_analysis": {
        "name": "Phân tích dữ liệu (Data Analysis)",
        "aliases": ["data analysis", "phan tich du lieu", "phân tích dữ liệu"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Phân tích dữ liệu là quá trình làm sạch, khám phá và diễn giải dữ liệu để rút ra thông tin hữu ích phục vụ ra quyết định. Thường dùng thống kê, trực quan hóa và công cụ như Excel, SQL, Python/Pandas.",
        "topics": ["Data Analysis", "Exploratory Data Analysis", "Statistical Analysis"],
        "related": ["data_science", "statistics", "data_visualization"],
    },
    "data_visualization": {
        "name": "Trực quan hóa dữ liệu (Data Visualization)",
        "aliases": ["data visualization", "truc quan hoa du lieu", "trực quan hóa dữ liệu", "visualization"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Trực quan hóa dữ liệu biến số liệu thành biểu đồ, đồ thị, dashboard để con người dễ nhận ra xu hướng và mẫu hình. Công cụ phổ biến: Tableau, Power BI, matplotlib, ggplot2.",
        "topics": ["Data Visualization", "Tableau", "Power BI"],
        "related": ["data_analysis", "tableau", "power_bi"],
    },
    "regression": {
        "name": "Hồi quy (Regression)",
        "aliases": ["regression", "hoi quy", "hồi quy", "regression analysis", "linear regression"],
        "category": "Trí tuệ nhân tạo", "level": "Cơ bản",
        "definition": "Hồi quy là nhóm thuật toán học có giám sát dự đoán giá trị LIÊN TỤC (vd giá nhà, doanh thu) từ các đặc trưng đầu vào. Hồi quy tuyến tính (linear regression) là dạng cơ bản nhất.",
        "topics": ["Regression", "Machine Learning"],
        "related": ["machine_learning", "classification", "statistics"],
    },
    "classification": {
        "name": "Phân loại (Classification)",
        "aliases": ["classification", "phan loai", "phân loại"],
        "category": "Trí tuệ nhân tạo", "level": "Cơ bản",
        "definition": "Phân loại là nhóm thuật toán học có giám sát gán NHÃN RỜI RẠC cho dữ liệu (vd spam/không spam, mèo/chó). Khác hồi quy ở chỗ đầu ra là lớp/nhãn thay vì số liên tục.",
        "topics": ["Classification", "Machine Learning"],
        "related": ["machine_learning", "regression", "supervised_learning"],
    },
    "statistics": {
        "name": "Thống kê (Statistics)",
        "aliases": ["statistics", "thong ke", "thống kê", "statistical analysis"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Thống kê là ngành thu thập, mô tả và suy luận từ dữ liệu (xác suất, phân phối, kiểm định giả thuyết). Là nền tảng toán học của khoa học dữ liệu và machine learning.",
        "topics": ["Statistical Analysis", "Statistics"],
        "related": ["data_science", "machine_learning", "data_analysis"],
    },
    "pandas": {
        "name": "Pandas",
        "aliases": ["pandas"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Pandas là thư viện Python xử lý dữ liệu dạng bảng (DataFrame): đọc/ghi CSV-Excel-SQL, lọc, nhóm, biến đổi và làm sạch dữ liệu. Công cụ chủ lực để phân tích dữ liệu bằng Python.",
        "topics": ["Data Manipulation", "Python Programming"],
        "related": ["python", "numpy", "data_analysis"],
    },
    "numpy": {
        "name": "NumPy",
        "aliases": ["numpy"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "NumPy là thư viện Python cho tính toán số học trên mảng/ma trận nhiều chiều, nhanh và hiệu quả. Là nền tảng của Pandas, scikit-learn và hầu hết hệ sinh thái khoa học dữ liệu Python.",
        "topics": ["Python Programming", "Data Manipulation"],
        "related": ["python", "pandas", "statistics"],
    },
    "predictive_modeling": {
        "name": "Mô hình dự báo (Predictive Modeling)",
        "aliases": ["predictive modeling", "mo hinh du bao", "mô hình dự báo", "predictive analytics"],
        "category": "Trí tuệ nhân tạo", "level": "Trung cấp",
        "definition": "Mô hình dự báo dùng dữ liệu lịch sử và machine learning để dự đoán kết quả tương lai (vd khách rời bỏ, nhu cầu bán hàng), qua các bước chuẩn bị dữ liệu, huấn luyện, đánh giá và triển khai mô hình.",
        "topics": ["Predictive Modeling", "Machine Learning"],
        "related": ["machine_learning", "regression", "data_science"],
    },
    "data_cleaning": {
        "name": "Làm sạch dữ liệu (Data Cleaning)",
        "aliases": ["data cleansing", "data cleaning", "lam sach du lieu", "làm sạch dữ liệu", "data wrangling"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Làm sạch dữ liệu là xử lý dữ liệu thiếu, trùng, sai định dạng hoặc ngoại lệ trước khi phân tích/huấn luyện. Chiếm phần lớn thời gian của dự án dữ liệu vì 'rác vào, rác ra'.",
        "topics": ["Data Cleansing", "Data Processing"],
        "related": ["data_analysis", "data_science", "feature_engineering"],
    },
    "data_engineering": {
        "name": "Kỹ thuật dữ liệu (Data Engineering)",
        "aliases": ["data engineering", "ky thuat du lieu", "kỹ thuật dữ liệu"],
        "category": "Khoa học dữ liệu", "level": "Nâng cao",
        "definition": "Kỹ thuật dữ liệu xây dựng và vận hành đường ống (pipeline) thu thập, lưu trữ và biến đổi dữ liệu ở quy mô lớn (ETL, data warehouse, data lake) để phục vụ phân tích và machine learning.",
        "topics": ["ETL", "Big Data", "Data Management"],
        "related": ["big_data", "data_science", "sql"],
    },
    "r_language": {
        "name": "Ngôn ngữ R",
        "aliases": ["r programming", "ngon ngu r", "ngôn ngữ r", "r language"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "R là ngôn ngữ lập trình chuyên cho thống kê và phân tích dữ liệu, mạnh về mô hình thống kê và trực quan hóa (ggplot2). Phổ biến trong nghiên cứu và khoa học dữ liệu.",
        "topics": ["R Programming", "Statistical Analysis"],
        "related": ["statistics", "data_science", "python"],
    },
    "tableau": {
        "name": "Tableau",
        "aliases": ["tableau"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Tableau là phần mềm trực quan hóa dữ liệu kéo-thả, tạo dashboard tương tác từ nhiều nguồn dữ liệu mà không cần lập trình nhiều. Phổ biến trong phân tích kinh doanh (BI).",
        "topics": ["Data Visualization", "Data Visualization Software"],
        "related": ["data_visualization", "data_analysis", "power_bi"],
    },
    "power_bi": {
        "name": "Power BI",
        "aliases": ["power bi", "powerbi"],
        "category": "Khoa học dữ liệu", "level": "Cơ bản",
        "definition": "Power BI là công cụ Business Intelligence của Microsoft để kết nối dữ liệu, tạo báo cáo và dashboard tương tác. Tích hợp tốt với hệ sinh thái Microsoft (Excel, Azure).",
        "topics": ["Data Visualization", "Data Visualization Software"],
        "related": ["data_visualization", "data_analysis", "tableau"],
    },
    "recommender_system": {
        "name": "Hệ thống gợi ý (Recommender System)",
        "aliases": ["recommender system", "recommendation system", "he goi y", "hệ gợi ý", "he thong goi y"],
        "category": "Trí tuệ nhân tạo", "level": "Trung cấp",
        "definition": "Hệ thống gợi ý dự đoán mục mà người dùng có thể thích (phim, sản phẩm, khóa học) dựa trên hành vi và đặc trưng. Hai hướng chính: lọc cộng tác (collaborative filtering) và lọc theo nội dung (content-based).",
        "topics": ["Machine Learning", "Recommender Systems"],
        "related": ["machine_learning", "data_science", "ai"],
    },
    "event_driven": {
        "name": "Kiến trúc hướng sự kiện (Event-driven)",
        "aliases": ["event driven", "event-driven", "huong su kien", "kien truc huong su kien"],
        "category": "Lập trình", "level": "Nâng cao",
        "definition": "Kiến trúc phần mềm trong đó các thành phần phản ứng theo SỰ KIỆN (event) thay vì gọi trực tiếp nhau, giúp hệ thống lỏng lẻo và dễ mở rộng. Thường dùng message queue như Kafka, RabbitMQ.",
        "topics": ["Microservices", "Kafka"],
        "related": ["microservices", "kafka", "api"],
    },
    "hosting": {
        "name": "Hosting (Lưu trữ web)",
        "aliases": ["hosting", "luu tru web", "web hosting"],
        "category": "DevOps", "level": "Cơ bản",
        "definition": "Dịch vụ lưu trữ website/ứng dụng trên máy chủ để truy cập qua internet. Các dạng phổ biến: shared hosting, VPS, cloud hosting.",
        "topics": ["Cloud Computing", "Deployment"],
        "related": ["cloud", "devops"],
    },
    "load_balancer": {
        "name": "Load Balancer (Cân bằng tải)",
        "aliases": ["load balancer", "can bang tai", "lb"],
        "category": "DevOps", "level": "Trung cấp",
        "definition": "Bộ cân bằng tải phân phối lưu lượng truy cập đến nhiều máy chủ để tránh quá tải, tăng khả năng chịu tải và độ sẵn sàng cao (high availability).",
        "topics": ["Scalability", "Networking"],
        "related": ["microservices", "devops"],
    },
    "middleware": {
        "name": "Middleware (Phần mềm trung gian)",
        "aliases": ["middleware", "phan mem trung gian"],
        "category": "Lập trình", "level": "Trung cấp",
        "definition": "Phần mềm nằm GIỮA các thành phần hệ thống, xử lý request trước/sau khi tới handler chính — ví dụ xác thực, logging, CORS, rate limiting trong web framework.",
        "topics": ["Backend", "API"],
        "related": ["api", "backend"],
    },
    "token": {
        "name": "Token",
        "aliases": ["token", "access token", "refresh token"],
        "category": "An ninh mạng", "level": "Cơ bản",
        "definition": "Chuỗi ký tự đại diện cho quyền truy cập hoặc danh tính người dùng, dùng trong xác thực/ủy quyền. Ví dụ phổ biến: JWT, access token, refresh token.",
        "topics": ["Authentication", "Security"],
        "related": ["jwt", "auth"],
    },
    "build_pipeline": {
        "name": "Build Pipeline",
        "aliases": ["build pipeline", "pipeline build", "duong ong build"],
        "category": "DevOps", "level": "Trung cấp",
        "definition": "Quy trình tự động biến mã nguồn thành sản phẩm chạy được: viết code → test → build → đóng gói → triển khai. Là trái tim của CI/CD.",
        "topics": ["CI/CD", "DevOps"],
        "related": ["ci_cd", "devops", "docker"],
    },
}


def main():
    data = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    concepts = data["concepts"]
    added = []
    for key, entry in NEW.items():
        if key in concepts:
            continue
        concepts[key] = entry
        added.append(key)
    for key in added:
        concepts[key]["related"] = [r for r in concepts[key]["related"] if r in concepts]

    backup = GLOSSARY.with_suffix(".beforeexpand.json")
    if not backup.exists():
        shutil.copy2(GLOSSARY, backup)
    GLOSSARY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] thêm {len(added)} khái niệm -> tổng {len(concepts)}. Backup: {backup.name}")
    print("  +", ", ".join(added))


if __name__ == "__main__":
    main()
