import sys
import time
import warnings
from kafka.errors import KafkaError

# Ẩn cảnh báo DeprecationWarning phiền phức của kafka-python cho toàn dự án
warnings.filterwarnings("ignore", category=DeprecationWarning, module="kafka")

def connect_kafka_with_retry(connect_func, retries=12, delay=5):
    """Bọc logic kết nối Kafka với cơ chế tự động thử lại."""
    for attempt in range(1, retries + 1):
        try:
            result = connect_func()
            print("✅ Đã kết nối thành công tới Kafka!")
            return result
        except KafkaError as e:
            print(f"  -> Lần thử {attempt}/{retries}: Kafka chưa sẵn sàng. Thử lại sau {delay}s... (Lỗi: {e})")
            time.sleep(delay)
            
    print(f"\nFATAL: Không thể kết nối tới Kafka sau {retries} lần thử. Exiting.")
    sys.exit(1)