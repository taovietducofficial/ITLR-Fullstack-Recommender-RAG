"""Dọn nhiễu console — gom 3 thứ VÔ HẠI nhưng gây rối log khi chạy app.

  1) InconsistentVersionWarning của scikit-learn: artifacts pickle ở sklearn 1.9.0
     nhưng runtime là 1.8.0. Đã re-pickle để đóng dấu đúng phiên bản (xem
     repickle_artifacts.py); filter dưới đây là lớp chắn cho mọi estimator còn sót.
  2) "LOAD REPORT ... position_ids UNEXPECTED" + thanh tiến trình tải trọng số:
     log dài dòng của transformers/sentence-transformers khi nạp model — chỉ giữ ERROR.
  3) ConnectionResetError [WinError 10054]: ProactorEventLoop của asyncio trên Windows
     ném ra khi trình duyệt đóng WebSocket đột ngột. KHÔNG phải lỗi ứng dụng -> nuốt.

Import module này TRƯỚC khi nạp model (đặt ở đầu app.py) để có hiệu lực sớm nhất.
"""

import logging
import sys
import warnings

try:
    from sklearn.exceptions import InconsistentVersionWarning

    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except Exception:
    pass

for _name in ("transformers", "sentence_transformers"):
    logging.getLogger(_name).setLevel(logging.ERROR)
try:
    from transformers.utils import logging as _hf_logging

    _hf_logging.set_verbosity_error()
    _hf_logging.disable_progress_bar()
except Exception:
    pass

if sys.platform.startswith("win"):
    import functools

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        def _silence_conn_reset(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except ConnectionResetError:
                    pass

            return wrapper

        _ProactorBasePipeTransport._call_connection_lost = _silence_conn_reset(
            _ProactorBasePipeTransport._call_connection_lost
        )
    except Exception:
        pass
