"""Sinh bộ dữ liệu khóa học & tài liệu CNTT — tối ưu cho hệ gợi ý.

    python generate_data.py [số_dòng]   # mặc định 50000

Mục tiêu chất lượng cho recommender:
  - ĐA DẠNG NGỮ NGHĨA: tiêu đề + mô tả phong phú (nhiều template, có cấp độ, đối
    tượng, mục tiêu, dự án) -> embeddings/TF-IDF phân biệt tốt, giảm trùng lặp.
  - CÓ TRƯỜNG `level` (Cơ bản/Trung cấp/Nâng cao): độ khó là DỮ LIỆU THẬT, giúp
    lộ trình học chính xác (không phải suy từ keyword tiêu đề).
  - NHẤT QUÁN: tiêu đề ↔ cấp độ ↔ mô tả khớp nhau (vd "Nhập môn X" luôn là Cơ bản).

Taxonomy bao phủ: ngôn ngữ lập trình, web, DSA, database, AI/ML, data science,
big data, cloud, devops, security, mobile, game, software engineering, CS nền tảng.
"""

import csv
import itertools
import random

random.seed(42)

CATEGORIES = {
    "Lập trình": {
        "topics": {
            "Cơ bản": ["Python", "C", "OOP", "Biến và Kiểu dữ liệu", "Vòng lặp và Điều kiện", "Hàm"],
            "Trung cấp": ["Java", "JavaScript", "C#", "Kotlin", "Go", "Data Structures"],
            "Nâng cao": ["C++", "Rust", "Functional Programming", "Concurrency", "Memory Management", "Algorithm"],
        },
        "platforms": ["Coursera", "Udemy", "edX", "freeCodeCamp", "GeeksforGeeks", "JetBrains Academy"],
        "instructors": [
            "Nguyễn Văn An", "Trần Thị Bình", "Lê Minh Cường", "Phạm Đức Dũng",
            "Robert C. Martin", "Bjarne Stroustrup", "Guido van Rossum",
        ],
    },
    "Lập trình Web": {
        "topics": {
            "Cơ bản": ["HTML", "CSS", "JavaScript", "Responsive Design"],
            "Trung cấp": ["TypeScript", "React", "Vue", "Node.js", "Express.js", "REST API"],
            "Nâng cao": ["Next.js", "NestJS", "GraphQL", "Spring Boot", "Microservices", "Web Performance"],
        },
        "platforms": ["MDN", "Udemy", "freeCodeCamp", "Frontend Masters", "W3Schools"],
        "instructors": [
            "Dan Abramov", "Evan You", "Mosh Hamedani", "Traversy Media",
            "Hoàng Thị Em", "Võ Văn Web", "Mozilla Team",
        ],
    },
    "Cấu trúc dữ liệu & Giải thuật": {
        "topics": {
            "Cơ bản": ["Array", "Linked List", "Stack", "Queue", "Hash Table", "Big-O"],
            "Trung cấp": ["Tree", "Binary Tree", "Heap", "Sorting", "Searching", "Binary Search", "Recursion"],
            "Nâng cao": ["Graph", "Trie", "DFS", "BFS", "Dynamic Programming", "Greedy Algorithm", "Backtracking", "Divide and Conquer"],
        },
        "platforms": ["LeetCode", "GeeksforGeeks", "Coursera", "Udemy", "HackerRank"],
        "instructors": [
            "Trần Văn Giải", "Lý Thị Thuật", "William Fiset", "Abdul Bari",
            "Nguyễn Đức Toán", "Tim Roughgarden",
        ],
    },
    "Cơ sở dữ liệu": {
        "topics": {
            "Cơ bản": ["SQL", "MySQL", "CRUD", "Join", "Data Modeling"],
            "Trung cấp": ["PostgreSQL", "Index", "Transaction", "Stored Procedure", "Normalization", "NoSQL", "MongoDB"],
            "Nâng cao": ["Query Optimization", "Sharding", "Replication", "Redis", "Cassandra", "Database Tuning"],
        },
        "platforms": ["SQLZoo", "MongoDB University", "edX", "Oracle Academy", "Udemy"],
        "instructors": [
            "Silberschatz", "Ngô Thị DB", "Trịnh Văn Minh", "Lý Thị Nga",
            "Oracle Team", "MongoDB Team",
        ],
    },
    "Trí tuệ nhân tạo": {
        "topics": {
            "Cơ bản": ["Python", "AI Basic", "Statistics", "Linear Algebra", "Pandas"],
            "Trung cấp": ["Machine Learning", "Scikit-learn", "Regression", "Classification", "Neural Network", "Feature Engineering"],
            "Nâng cao": ["Deep Learning", "NLP", "Computer Vision", "Transformer", "LLM", "RAG", "Generative AI", "Fine-tuning"],
        },
        "platforms": ["Coursera", "fast.ai", "DeepLearning.AI", "Kaggle", "Stanford Online"],
        "instructors": [
            "Andrew Ng", "Vũ Quang Phúc", "Đỗ Thanh Hùng", "Ian Goodfellow",
            "Yann LeCun", "Fei-Fei Li", "Bùi Văn AI",
        ],
    },
    "Khoa học dữ liệu": {
        "topics": {
            "Cơ bản": ["Excel", "SQL", "Statistics", "Pandas", "NumPy"],
            "Trung cấp": ["Data Analysis", "Data Visualization", "Matplotlib", "Power BI", "Tableau", "Feature Engineering"],
            "Nâng cao": ["ETL", "Data Pipeline", "Data Warehouse", "Spark", "Airflow", "Machine Learning"],
        },
        "platforms": ["Kaggle Learn", "DataCamp", "Coursera", "Databricks", "Udemy"],
        "instructors": [
            "Lý Thị Phương", "Mai Văn Giang", "Phan Thị Hà", "Hadley Wickham",
            "Wes McKinney", "Nguyễn Thị Data",
        ],
    },
    "Dữ liệu lớn": {
        "topics": {
            "Cơ bản": ["Big Data", "SQL", "Linux", "Distributed System Basics"],
            "Trung cấp": ["Hadoop", "MapReduce", "Hive", "Data Lake", "Data Warehouse"],
            "Nâng cao": ["Spark", "Kafka", "Flink", "Stream Processing", "HBase", "Cassandra"],
        },
        "platforms": ["Databricks", "Cloudera", "Coursera", "Apache Foundation", "Udemy"],
        "instructors": [
            "Matei Zaharia", "Trần Văn Bigdata", "Doug Cutting", "Lê Thị Spark",
            "Confluent Team",
        ],
    },
    "Điện toán đám mây": {
        "topics": {
            "Cơ bản": ["Cloud Concepts", "Linux", "Networking Basics", "IAM"],
            "Trung cấp": ["AWS", "EC2", "S3", "Docker", "Load Balancing", "CDN"],
            "Nâng cao": ["Kubernetes", "Serverless", "Lambda", "Cloud Architecture", "Terraform", "Multi-cloud"],
        },
        "platforms": ["AWS Training", "Microsoft Learn", "Google Cloud Skills", "A Cloud Guru"],
        "instructors": [
            "Nguyễn Văn Phúc", "Trần Thị Quỳnh", "Lê Văn Sơn", "AWS Team",
            "Google Cloud Team",
        ],
    },
    "DevOps": {
        "topics": {
            "Cơ bản": ["Git", "GitHub", "Linux", "Bash", "CI/CD Basics"],
            "Trung cấp": ["Docker", "GitHub Actions", "Jenkins", "GitLab", "Monitoring"],
            "Nâng cao": ["Kubernetes", "Terraform", "Ansible", "Infrastructure as Code", "Prometheus", "Grafana", "Helm"],
        },
        "platforms": ["Docker Docs", "Kubernetes.io", "Pluralsight", "GitHub Skills", "HashiCorp Learn"],
        "instructors": [
            "Nguyễn Thị Vân", "Trần Văn Xuân", "Lê Thị Yến", "Kelsey Hightower",
            "Mitchell Hashimoto",
        ],
    },
    "An ninh mạng": {
        "topics": {
            "Cơ bản": ["Network Security", "Cryptography", "Linux", "OWASP"],
            "Trung cấp": ["Web Security", "Ethical Hacking", "Wireshark", "Burp Suite", "Firewall"],
            "Nâng cao": ["Penetration Testing", "Malware Analysis", "Kali Linux", "Incident Response", "Threat Hunting"],
        },
        "platforms": ["TryHackMe", "HackTheBox", "OWASP", "SANS", "Cybrary"],
        "instructors": [
            "Quách Thị Quỳnh", "Đinh Văn Sơn", "Kevin Mitnick", "OWASP Team",
            "Mai Văn Security",
        ],
    },
    "Lập trình Mobile": {
        "topics": {
            "Cơ bản": ["Mobile Basics", "Java", "Kotlin", "UI Layout"],
            "Trung cấp": ["Android", "Jetpack Compose", "Firebase", "REST API"],
            "Nâng cao": ["iOS", "Swift", "SwiftUI", "Flutter", "React Native", "Cross-platform"],
        },
        "platforms": ["Google Codelabs", "Apple Developer", "Udemy", "Flutter.dev"],
        "instructors": [
            "Google Android Team", "Apple Developer Team", "Bùi Văn Mobile",
            "Angela Yu", "Maximilian Schwarzmüller",
        ],
    },
    "Phát triển Game": {
        "topics": {
            "Cơ bản": ["Game Design", "C#", "Unity Basics", "2D Graphics"],
            "Trung cấp": ["Unity", "Game Physics", "Level Design", "Animation"],
            "Nâng cao": ["Unreal Engine", "C++", "Shader", "3D Graphics", "Multiplayer", "Optimization"],
        },
        "platforms": ["Unity Learn", "Unreal Online Learning", "Udemy", "GameDev.tv"],
        "instructors": [
            "Brackeys", "Trần Văn Game", "Sebastian Lague", "Nguyễn Thị Unity",
            "GameDev.tv Team",
        ],
    },
    "Kỹ thuật phần mềm": {
        "topics": {
            "Cơ bản": ["OOP", "Clean Code", "Git", "SOLID"],
            "Trung cấp": ["Design Pattern", "MVC", "Refactoring", "API Design", "Unit Testing"],
            "Nâng cao": ["Software Architecture", "Microservices", "Event Driven", "Distributed System", "Domain Driven Design", "CQRS"],
        },
        "platforms": ["O'Reilly", "ByteByteGo", "microservices.io", "Pluralsight"],
        "instructors": [
            "Martin Fowler", "Robert C. Martin", "Alex Xu", "Chris Richardson",
            "Sam Newman", "Eric Evans",
        ],
    },
    "Khoa học máy tính": {
        "topics": {
            "Cơ bản": ["Computer Architecture", "Binary", "Process", "Memory Management"],
            "Trung cấp": ["Operating System", "Computer Network", "TCP/IP", "Thread", "Concurrency"],
            "Nâng cao": ["Compiler", "Distributed System", "Theory of Computation", "Parallel Computing"],
        },
        "platforms": ["MIT OpenCourseWare", "Coursera", "edX", "Stanford Online"],
        "instructors": [
            "Silberschatz", "Tanenbaum", "Kurose Ross", "Tô Thị Tuyết",
            "Nguyễn Văn Nền Tảng",
        ],
    },
    "Mạng máy tính": {
        "topics": {
            "Cơ bản": ["TCP/IP", "OSI Model", "DNS", "DHCP", "IP Addressing"],
            "Trung cấp": ["Routing", "Switching", "Subnetting", "VLAN", "VPN", "Wireshark"],
            "Nâng cao": ["BGP", "OSPF", "SDN", "Load Balancer", "Network Troubleshooting", "Proxy"],
        },
        "platforms": ["Cisco Networking Academy", "Coursera", "Udemy", "INE", "Pluralsight"],
        "instructors": [
            "Cisco Team", "Nguyễn Văn Mạng", "Todd Lammle", "Jeremy Cioara", "Lê Thị Net",
        ],
    },
    "Kiểm thử phần mềm": {
        "topics": {
            "Cơ bản": ["Manual Testing", "QA Process", "Bug Tracking", "Test Case Design"],
            "Trung cấp": ["Unit Testing", "JUnit", "PyTest", "Postman", "Selenium", "Integration Testing"],
            "Nâng cao": ["Test Automation", "Cypress", "Playwright", "TDD", "BDD", "Performance Testing", "JMeter"],
        },
        "platforms": ["Test Automation University", "Udemy", "Coursera", "Ministry of Testing"],
        "instructors": [
            "Angie Jones", "Nguyễn Thị QA", "Trần Văn Test", "Katalon Team", "Lisa Crispin",
        ],
    },
    "Thiết kế UI/UX": {
        "topics": {
            "Cơ bản": ["Design Thinking", "Wireframing", "Figma", "Visual Design"],
            "Trung cấp": ["Prototyping", "User Research", "Usability", "Information Architecture"],
            "Nâng cao": ["Design System", "Interaction Design", "Accessibility", "UX Strategy"],
        },
        "platforms": ["Interaction Design Foundation", "Coursera", "Udemy", "Figma Learn"],
        "instructors": [
            "Don Norman", "Nguyễn Thị Design", "Trần Văn UX", "Google UX Team", "Steve Krug",
        ],
    },
    "Blockchain & Web3": {
        "topics": {
            "Cơ bản": ["Blockchain", "Bitcoin", "Cryptocurrency", "Consensus"],
            "Trung cấp": ["Ethereum", "Smart Contract", "Solidity", "Web3", "Hardhat"],
            "Nâng cao": ["DeFi", "NFT", "DApp", "Tokenomics", "Hyperledger", "Security Audit"],
        },
        "platforms": ["Alchemy University", "Cyfrin Updraft", "Coursera", "Udemy"],
        "instructors": [
            "Vitalik Buterin", "Nguyễn Văn Chain", "Patrick Collins", "Andreas Antonopoulos",
        ],
    },
    "IoT & Hệ thống nhúng": {
        "topics": {
            "Cơ bản": ["IoT", "Arduino", "Microcontroller", "Sensor"],
            "Trung cấp": ["Raspberry Pi", "ESP32", "Embedded C", "MQTT", "Firmware"],
            "Nâng cao": ["RTOS", "FreeRTOS", "Edge Computing", "PCB Design", "Bluetooth"],
        },
        "platforms": ["Arduino", "Coursera", "Udemy", "edX"],
        "instructors": [
            "Nguyễn Văn Nhúng", "Massimo Banzi", "Trần Thị IoT", "ARM Team",
        ],
    },
    "MLOps & AI Engineering": {
        "topics": {
            "Cơ bản": ["Machine Learning", "Python", "Docker", "Git"],
            "Trung cấp": ["Model Deployment", "MLflow", "Model Serving", "Experiment Tracking", "CI/CD for ML"],
            "Nâng cao": ["Kubeflow", "Feature Store", "Model Monitoring", "LLMOps", "Vector Database", "SageMaker", "Vertex AI"],
        },
        "platforms": ["DeepLearning.AI", "Coursera", "Weights & Biases", "Udemy"],
        "instructors": [
            "Andrew Ng", "Chip Huyen", "Nguyễn Văn MLOps", "Goku Mohandas",
        ],
    },
    "Quản trị hệ thống & Linux": {
        "topics": {
            "Cơ bản": ["Linux", "Bash", "Shell Scripting", "SSH", "Cron"],
            "Trung cấp": ["System Administration", "systemd", "Nginx", "Apache", "Server Management"],
            "Nâng cao": ["Virtualization", "VMware", "Backup", "Monitoring", "High Availability"],
        },
        "platforms": ["Red Hat Training", "Udemy", "Coursera", "Linux Foundation"],
        "instructors": [
            "Linus Torvalds", "Nguyễn Văn Linux", "Red Hat Team", "Sander van Vugt",
        ],
    },
    "Quản lý dự án CNTT": {
        "topics": {
            "Cơ bản": ["Project Management", "Agile", "Scrum", "Kanban"],
            "Trung cấp": ["Jira", "Sprint Planning", "Product Owner", "Scrum Master", "Roadmap"],
            "Nâng cao": ["Risk Management", "Stakeholder Management", "PMP", "Waterfall", "Program Management"],
        },
        "platforms": ["Scrum.org", "Coursera", "PMI", "Udemy"],
        "instructors": [
            "Nguyễn Thị PM", "Scrum.org Team", "Mike Cohn", "Jeff Sutherland",
        ],
    },
    "AR/VR & Thực tế ảo": {
        "topics": {
            "Cơ bản": ["Virtual Reality", "Augmented Reality", "3D Modeling", "Unity Basics"],
            "Trung cấp": ["Unity XR", "ARKit", "ARCore", "VR Interaction"],
            "Nâng cao": ["Spatial Computing", "Mixed Reality", "WebXR", "Metaverse", "Oculus"],
        },
        "platforms": ["Unity Learn", "Coursera", "Udemy", "Meta Learn"],
        "instructors": [
            "Nguyễn Văn VR", "Meta Reality Team", "Unity XR Team", "Trần Thị AR",
        ],
    },
    "Đồ họa máy tính": {
        "topics": {
            "Cơ bản": ["Computer Graphics", "3D Math", "Image Processing", "Blender"],
            "Trung cấp": ["OpenGL", "WebGL", "Rendering", "Shader", "Texture Mapping"],
            "Nâng cao": ["Vulkan", "Ray Tracing", "GPU Programming", "Real-time Rendering"],
        },
        "platforms": ["Scratchapixel", "Coursera", "Udemy", "edX"],
        "instructors": [
            "Nguyễn Văn Đồ Họa", "Pixar Team", "John Carmack", "Cem Yuksel",
        ],
    },
    "Phân tích nghiệp vụ (BA)": {
        "topics": {
            "Cơ bản": ["Business Analysis", "Requirements Engineering", "Documentation", "Use Case"],
            "Trung cấp": ["UML", "BPMN", "User Story", "Process Modeling", "SQL"],
            "Nâng cao": ["Stakeholder Analysis", "Gap Analysis", "Data Analysis", "Solution Design"],
        },
        "platforms": ["IIBA", "Coursera", "Udemy", "edX"],
        "instructors": [
            "Nguyễn Thị BA", "IIBA Team", "Trần Văn Nghiệp Vụ", "Barbara Carkenord",
        ],
    },
    "Điện toán lượng tử": {
        "topics": {
            "Cơ bản": ["Quantum Computing", "Qubit", "Superposition", "Entanglement"],
            "Trung cấp": ["Qiskit", "Quantum Gate", "Quantum Circuit", "Quantum Algorithm"],
            "Nâng cao": ["Shor Algorithm", "Grover Algorithm", "Quantum Cryptography", "Quantum Error Correction"],
        },
        "platforms": ["IBM Quantum", "Coursera", "edX", "Microsoft Quantum"],
        "instructors": [
            "IBM Quantum Team", "Nguyễn Văn Lượng Tử", "Microsoft Quantum Team", "John Preskill",
        ],
    },
}

LEVELS = [
    ("Cơ bản", 0.42),
    ("Trung cấp", 0.36),
    ("Nâng cao", 0.22),
]

LEVEL_CONFIG = {
    "Cơ bản": {
        "course_prefixes": ["Nhập môn", "Cơ bản", "Làm quen với", "Bắt đầu với",
                            "Khóa học vỡ lòng", "Cho người mới học"],
        "doc_prefixes": ["Giáo trình nhập môn", "Tài liệu cơ bản", "Sách nhập môn",
                         "Cẩm nang cho người mới", "Hướng dẫn bắt đầu"],
        "audiences": ["cho người mới bắt đầu", "cho người chưa có nền tảng lập trình",
                      "cho sinh viên năm nhất", "cho người tự học không cần kinh nghiệm"],
        "adjs": ["từ con số 0", "theo từng bước dễ hiểu", "với nền tảng vững chắc",
                 "giải thích trực quan"],
        "outcomes": ["tự tin viết những dòng {topic} đầu tiên",
                     "nắm chắc các khái niệm cốt lõi",
                     "có nền tảng vững để học tiếp các chủ đề nâng cao",
                     "hiểu rõ {topic} hoạt động như thế nào"],
    },
    "Trung cấp": {
        "course_prefixes": ["Thực hành", "Xây dựng", "Phát triển ứng dụng",
                            "Toàn diện", "Lộ trình", "Dự án thực tế với"],
        "doc_prefixes": ["Tài liệu thực hành", "Sổ tay", "Hướng dẫn chuyên đề",
                         "Sách thực chiến", "Tuyển tập bài tập"],
        "audiences": ["cho lập trình viên đã có nền tảng", "cho người muốn lên trình",
                      "cho developer đang đi làm", "cho sinh viên chuẩn bị thực tập"],
        "adjs": ["hướng dự án thực tế", "qua nhiều bài lab", "bám sát công việc thực tế",
                 "kết hợp lý thuyết và thực hành"],
        "outcomes": ["tự xây dựng được một ứng dụng {topic} hoàn chỉnh",
                     "áp dụng {topic} vào dự án thực tế",
                     "thành thạo các kỹ thuật và pattern phổ biến",
                     "đủ khả năng nhận các task thực tế về {topic}"],
    },
    "Nâng cao": {
        "course_prefixes": ["Nâng cao", "Chuyên sâu", "Masterclass", "Kiến trúc",
                            "Tối ưu", "Thực chiến production"],
        "doc_prefixes": ["Tài liệu chuyên sâu", "Sách nâng cao", "Reference chuyên gia",
                         "Cẩm nang kiến trúc", "Tuyển tập kỹ thuật nâng cao"],
        "audiences": ["cho kỹ sư giàu kinh nghiệm", "cho senior developer",
                      "cho người chuẩn bị phỏng vấn big tech", "cho kiến trúc sư hệ thống"],
        "adjs": ["ở quy mô lớn", "tối ưu hiệu năng", "chuẩn production",
                 "đi sâu vào nội tại"],
        "outcomes": ["thiết kế và vận hành {topic} ở quy mô lớn",
                     "tối ưu hiệu năng và xử lý các bài toán khó",
                     "làm chủ kiến trúc và các kỹ thuật nâng cao",
                     "đạt trình độ chuyên gia về {topic}"],
    },
}

ANGLES = [
    "qua dự án thực tế", "theo lộ trình bài bản", "chuẩn phỏng vấn",
    "từ A đến Z", "kèm bài tập", "thực chiến", "tinh gọn",
    "trong 30 ngày", "bằng ví dụ thực tế", "cấp tốc", "toàn tập",
    "có chứng chỉ", "ôn thi", "cho đồ án",
]

DESC_TEMPLATES = [
    "{prefix_phrase} {topic} {adj}, đi qua {t2} và {t3}. Sau khi hoàn thành, bạn sẽ {outcome}.",
    "Học {topic} {audience}: tập trung vào {t2}, {t3} và thực hành qua các bài lab. Mục tiêu giúp bạn {outcome}.",
    "Tài liệu về {topic} bám sát thực tế, kết hợp lý thuyết {t2} với ví dụ {t3} trong lĩnh vực {category}. Phù hợp {audience}.",
    "Lộ trình {topic} {adj}: từ {t2} đến {t3}, kèm bài tập và một dự án nhỏ để bạn {outcome}.",
    "Khám phá {topic} cùng {t2} và {t3} qua các tình huống thực tế trong {category}. Hướng tới việc bạn {outcome}.",
    "Nội dung {topic} được biên soạn {adj}, làm rõ mối liên hệ giữa {t2} và {t3}. Dành {audience}.",
    "Tổng hợp kiến thức {topic} trong {category}: {t2}, {t3}, best practices và các lỗi thường gặp. Giúp bạn {outcome}.",
    "Đi sâu vào {topic} với trọng tâm {t2} và {t3}, minh họa bằng case study thực tế. Sau khóa học bạn sẽ {outcome}.",
    "{prefix_phrase} {topic} {adj} dành {audience}, có ví dụ {t2} và bài thực hành {t3} ở cuối mỗi chương.",
    "Cẩm nang {topic} cô đọng: nắm nhanh {t2}, {t3} và cách vận dụng vào {category}. Mục tiêu để bạn {outcome}.",
]

LINK_TEMPLATES = {
    "Coursera": "https://www.coursera.org/learn/{slug}",
    "Udemy": "https://www.udemy.com/course/{slug}",
    "edX": "https://www.edx.org/learn/{slug}",
    "freeCodeCamp": "https://www.freecodecamp.org/learn/{slug}",
    "MDN": "https://developer.mozilla.org/docs/{slug}",
    "Kaggle": "https://www.kaggle.com/learn/{slug}",
    "GitHub Skills": "https://skills.github.com/{slug}",
    "Microsoft Learn": "https://learn.microsoft.com/training/{slug}",
    "AWS Training": "https://aws.amazon.com/training/{slug}",
    "Docker Docs": "https://docs.docker.com/{slug}",
    "Kubernetes.io": "https://kubernetes.io/docs/{slug}",
    "LeetCode": "https://leetcode.com/studyplan/{slug}",
    "default": "https://example.com/it/{slug}",
}

_LEVEL_NAMES = [lv for lv, _ in LEVELS]
_LEVEL_WEIGHTS = [w for _, w in LEVELS]


def slugify(text):
    return text.lower().replace(" ", "-").replace("/", "-").replace(".", "")[:48]


def make_link(platform, title):
    template = LINK_TEMPLATES.get(platform, LINK_TEMPLATES["default"])
    return template.format(slug=slugify(title))


def pick_track_topics(topics_by_level, level, n=4):
    """Chọn chủ đề MẠCH LẠC theo cấp độ -> lộ trình đúng tầng.

    - Chủ đề CHÍNH (đầu danh sách) luôn lấy từ bucket ĐÚNG cấp độ -> tiêu đề "Nhập môn X"
      gắn X cơ bản, "Chuyên sâu Z" gắn Z nâng cao.
    - Thêm 1 chủ đề NỀN TẢNG từ cấp dưới làm tiền đề -> mô tả có tính bắc cầu lộ trình.
    - Bù cho đủ n từ cùng cấp rồi toàn taxonomy của lĩnh vực (đảm bảo >= 3 chủ đề).
    """
    order = ["Cơ bản", "Trung cấp", "Nâng cao"]
    li = order.index(level)
    cur = topics_by_level[level][:]
    random.shuffle(cur)
    chosen = cur[: max(1, n - 1)]
    if li > 0 and topics_by_level[order[li - 1]]:
        prereq = random.choice(topics_by_level[order[li - 1]])
        if prereq not in chosen:
            chosen.append(prereq)
    backup = cur + [t for lv in order for t in topics_by_level[lv]]
    for t in backup:
        if len(chosen) >= n:
            break
        if t not in chosen:
            chosen.append(t)
    return chosen[:n]


def make_title(item_type, level, main_topic, category):
    cfg = LEVEL_CONFIG[level]
    prefix_pool = cfg["course_prefixes"] if item_type == "Khóa học" else cfg["doc_prefixes"]
    title = f"{random.choice(prefix_pool)} {main_topic}"
    r = random.random()
    if r < 0.22:
        title += f" cho {category}"
    elif r < 0.46:
        title += f" {random.choice(ANGLES)}"
    elif r < 0.60:
        title += f" {random.choice(cfg['audiences'])}"
    return title


def make_description(item_type, level, topics, category):
    cfg = LEVEL_CONFIG[level]
    topic, t2, t3 = topics[0], topics[1], topics[2]
    template = random.choice(DESC_TEMPLATES)
    prefix_phrase = (
        random.choice(["Khóa học", "Chương trình", "Lộ trình học"])
        if item_type == "Khóa học"
        else random.choice(["Tài liệu", "Giáo trình", "Cuốn sách"])
    )
    outcome = random.choice(cfg["outcomes"]).format(topic=topic)
    desc = template.format(
        prefix_phrase=prefix_phrase,
        topic=topic, t2=t2, t3=t3, category=category,
        adj=random.choice(cfg["adjs"]),
        audience=random.choice(cfg["audiences"]),
        outcome=outcome,
    )
    return desc[0].upper() + desc[1:]


def generate_items(target=10000):
    items = []
    item_id = 1
    used_titles = set()

    cat_names = list(CATEGORIES.keys())
    combos = list(itertools.product(cat_names, ["Khóa học", "Tài liệu"]))

    while len(items) < target:
        category, item_type = random.choice(combos)
        meta = CATEGORIES[category]
        level = random.choices(_LEVEL_NAMES, weights=_LEVEL_WEIGHTS, k=1)[0]

        topics = pick_track_topics(meta["topics"], level, 4)
        main_topic = topics[0]
        extra_topics = ", ".join(topics)

        title = make_title(item_type, level, main_topic, category)
        base_title = title
        suffix = 1
        while title in used_titles:
            suffix += 1
            title = f"{base_title} ({suffix})"
        used_titles.add(title)

        platform = random.choice(meta["platforms"])
        instructor = random.choice(meta["instructors"])
        description = make_description(item_type, level, topics, category)
        link = make_link(platform, title)

        items.append({
            "item_id": item_id,
            "title": title,
            "type": item_type,
            "level": level,
            "description": description,
            "category": category,
            "topics": extra_topics,
            "instructor": instructor,
            "platform": platform,
            "link": link,
        })
        item_id += 1

    return items


def main():
    import os
    import sys
    from collections import Counter

    from itlr import config

    target = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    items = generate_items(target)
    fieldnames = [
        "item_id", "title", "type", "level", "description", "category",
        "topics", "instructor", "platform", "link",
    ]
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.ITEMS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)

    courses = sum(1 for i in items if i["type"] == "Khóa học")
    docs = sum(1 for i in items if i["type"] == "Tài liệu")
    levels = Counter(i["level"] for i in items)
    uniq = len({i["title"] for i in items})
    print(f"Generated {len(items)} items -> {config.ITEMS_CSV}")
    print(f"  Khóa học: {courses} | Tài liệu: {docs} | Chuyên mục: {len(CATEGORIES)}")
    print("  Cấp độ: " + " | ".join(f"{k}: {levels[k]}" for k in _LEVEL_NAMES))
    print(f"  Tiêu đề duy nhất: {uniq} ({uniq / len(items) * 100:.1f}%)")


if __name__ == "__main__":
    main()
