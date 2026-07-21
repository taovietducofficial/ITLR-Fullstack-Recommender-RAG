"""Chạy TOÀN BỘ pipeline build artifacts theo đúng thứ tự phụ thuộc.

    python scripts/build_all.py            # dùng mặc định (50000 items)
    python scripts/build_all.py 5000       # số items nhỏ hơn cho dev/test

Thứ tự: generate_items -> build_model -> build_embeddings -> generate_interactions -> build_cf.
Lưu ý: build_embeddings có thể mất ~30 phút ở quy mô 50k (mã hóa embedding).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    n = sys.argv[1] if len(sys.argv) > 1 else None

    from itlr.data import generate_interactions, generate_items
    from itlr.pipelines import build_cf, build_embeddings, build_model

    if n:
        sys.argv = [sys.argv[0], n]

    print("1/5 generate_items");        generate_items.main()
    sys.argv = [sys.argv[0]]
    print("2/5 build_model");           build_model.main()
    print("3/5 build_embeddings");      build_embeddings.main()
    print("4/5 generate_interactions"); generate_interactions.main()
    print("5/5 build_cf");              build_cf.main()
    print("Hoàn tất build toàn bộ artifacts.")


if __name__ == "__main__":
    main()
