"""Đưa thư mục gốc dự án vào sys.path để test import được package `itlr`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
